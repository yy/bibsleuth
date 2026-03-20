"""Concurrent multi-database citation existence verification."""

from __future__ import annotations

import asyncio

from ..config import Config
from ..parse.extract_ids import extract_ids
from ..providers.base import BaseProvider, ProviderError
from ..types import BibEntry, Candidate, Verdict, VerifyResult
from .scoring import score_candidate


async def _check_entry_against_provider(
    entry: BibEntry,
    provider: BaseProvider,
) -> list[Candidate]:
    """Query a single provider for a single entry."""
    candidates: list[Candidate] = []

    # Try ID-based lookup first
    ids = extract_ids(entry.raw or "")
    if entry.doi:
        ids.setdefault("doi", entry.doi)

    for id_type, identifier in ids.items():
        try:
            results = await provider.lookup_by_id(identifier, id_type)
            candidates.extend(results)
        except ProviderError:
            pass

    # Fall back to title search
    if not candidates and entry.title:
        try:
            year = int(entry.year) if entry.year else None
            results = await provider.search(
                title=entry.title,
                authors=entry.authors[:1] if entry.authors else None,
                year=year,
            )
            candidates.extend(results)
        except ProviderError:
            pass

    return candidates


async def verify_entry(
    entry: BibEntry,
    providers: list[BaseProvider],
    config: Config,
) -> VerifyResult:
    """Verify a single entry against all providers concurrently."""
    tasks = [_check_entry_against_provider(entry, provider) for provider in providers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_candidates: list[Candidate] = []
    for result in results:
        if isinstance(result, list):
            all_candidates.extend(result)

    if not all_candidates:
        return VerifyResult(
            key=entry.key,
            verdict=Verdict.UNVERIFIED,
            reasons=["Not found in any database"],
        )

    # Score candidates
    ref_fields = {
        "title": entry.title,
        "authors": entry.authors,
        "year": entry.year,
        "venue": entry.venue,
    }

    best_score = 0.0
    best_candidate = None
    scored_candidates: list[Candidate] = []

    for candidate in all_candidates:
        cand_fields = {
            "title": candidate.title or "",
            "authors": candidate.authors,
            "year": candidate.year,
            "venue": candidate.venue or "",
        }
        score, _ = score_candidate(ref_fields, cand_fields)
        scored_candidates.append(candidate)
        if score > best_score:
            best_score = score
            best_candidate = candidate

    # Determine verdict
    if best_score >= config.verified_threshold:
        verdict = Verdict.VERIFIED
        reasons = [f"Matched with score {best_score:.2f}"]
    elif best_score >= config.likely_threshold:
        verdict = Verdict.LIKELY
        reasons = [f"Likely match with score {best_score:.2f}"]
    else:
        verdict = Verdict.UNVERIFIED
        reasons = [f"Best score {best_score:.2f} below threshold"]

    # Build patch from best candidate
    patch: dict[str, str] = {}
    if best_candidate and verdict in (Verdict.VERIFIED, Verdict.LIKELY):
        if best_candidate.ids.get("doi") and not entry.doi:
            patch["doi"] = best_candidate.ids["doi"]
        if best_candidate.url:
            patch["url"] = best_candidate.url

    return VerifyResult(
        key=entry.key,
        verdict=verdict,
        score=best_score,
        reasons=reasons,
        candidates=scored_candidates[:5],
        patch=patch,
    )


async def verify_entries(
    entries: list[BibEntry],
    providers: list[BaseProvider],
    config: Config,
) -> list[VerifyResult]:
    """Verify all entries concurrently."""
    tasks = [verify_entry(entry, providers, config) for entry in entries]
    return await asyncio.gather(*tasks)

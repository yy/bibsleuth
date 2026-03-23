"""Concurrent multi-database citation existence verification."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from ..config import Config
from ..parse.extract_ids import extract_ids
from ..providers.base import BaseProvider, ProviderError
from ..types import BibEntry, Candidate, Verdict, VerifyResult
from .scoring import score_candidate


@dataclass
class ProviderCheckResult:
    provider: str
    candidates: list[Candidate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    had_successful_query: bool = False


async def _check_entry_against_provider(
    entry: BibEntry,
    provider: BaseProvider,
) -> ProviderCheckResult:
    """Query a single provider for a single entry."""
    result = ProviderCheckResult(provider=provider.provider_name)

    # Try ID-based lookup first
    ids = extract_ids(entry.raw or "")
    if entry.doi:
        ids.setdefault("doi", entry.doi)

    for id_type, identifier in ids.items():
        try:
            candidates = await provider.lookup_by_id(identifier, id_type)
            result.had_successful_query = True
            result.candidates.extend(candidates)
        except ProviderError as exc:
            result.errors.append(f"{provider.provider_name}: {exc}")

    # Fall back to title search
    if not result.candidates and entry.title:
        try:
            year = int(entry.year) if entry.year else None
            candidates = await provider.search(
                title=entry.title,
                authors=entry.authors[:1] if entry.authors else None,
                year=year,
            )
            result.had_successful_query = True
            result.candidates.extend(candidates)
        except ProviderError as exc:
            result.errors.append(f"{provider.provider_name}: {exc}")

    return result


async def verify_entry(
    entry: BibEntry,
    providers: list[BaseProvider],
    config: Config,
) -> VerifyResult:
    """Verify a single entry against all providers concurrently."""
    tasks = [_check_entry_against_provider(entry, provider) for provider in providers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    checks: list[ProviderCheckResult] = []
    for provider, result in zip(providers, results, strict=False):
        if isinstance(result, ProviderCheckResult):
            checks.append(result)
            continue
        if isinstance(result, Exception):
            checks.append(
                ProviderCheckResult(
                    provider=provider.provider_name,
                    errors=[f"{provider.provider_name}: {result}"],
                )
            )

    all_candidates: list[Candidate] = []
    errors: list[str] = []
    successful_queries = 0
    for check in checks:
        all_candidates.extend(check.candidates)
        errors.extend(check.errors)
        if check.had_successful_query:
            successful_queries += 1

    all_candidates = _dedupe_candidates(all_candidates)

    if not all_candidates:
        if successful_queries == 0 and errors:
            return VerifyResult(
                key=entry.key,
                verdict=Verdict.ERROR,
                reasons=errors[:3],
            )

        reasons = ["Not found in any database"]
        reasons.extend(errors[:2])
        return VerifyResult(
            key=entry.key,
            verdict=Verdict.UNVERIFIED,
            reasons=reasons,
        )

    # Score candidates
    ref_fields = {
        "title": entry.title,
        "authors": entry.authors,
        "year": entry.year,
        "venue": entry.venue,
    }

    ranked_candidates = _rank_candidates(ref_fields, all_candidates)
    best_score, best_candidate = ranked_candidates[0]
    scored_candidates = [candidate for _, candidate in ranked_candidates]

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


def _rank_candidates(
    ref_fields: dict[str, object],
    candidates: list[Candidate],
) -> list[tuple[float, Candidate]]:
    ranked: list[tuple[float, Candidate]] = []
    for candidate in candidates:
        cand_fields = {
            "title": candidate.title or "",
            "authors": candidate.authors,
            "year": candidate.year,
            "venue": candidate.venue or "",
        }
        score, _ = score_candidate(ref_fields, cand_fields)
        ranked.append((score, candidate))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked


def _dedupe_candidates(candidates: list[Candidate]) -> list[Candidate]:
    unique: list[Candidate] = []
    seen: set[tuple[str, str]] = set()

    for candidate in candidates:
        identity = (
            candidate.provider,
            candidate.provider_id
            or candidate.ids.get("doi")
            or candidate.url
            or candidate.title
            or "",
        )
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(candidate)

    return unique

"""Concurrent multi-database citation existence verification."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from ..config import Config
from ..parse.extract_ids import extract_ids
from ..providers.base import BaseProvider, ProviderError
from ..types import (
    BibEntry,
    Candidate,
    EntryCategory,
    Verdict,
    VerifyResult,
    classify_entry_type,
)
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


def _filter_providers(
    entry: BibEntry,
    providers: list[BaseProvider],
    category: EntryCategory,
) -> list[BaseProvider]:
    """Filter providers based on entry category and available IDs."""
    cat_value = category.value
    ids = extract_ids(entry.raw or "")
    if entry.doi:
        ids.setdefault("doi", entry.doi)

    filtered = []
    for p in providers:
        if cat_value not in p.supported_categories:
            continue
        # Skip arXiv for entries without arXiv IDs (3s/req, poor title search)
        if p.provider_name == "arxiv" and "arxiv" not in ids:
            continue
        filtered.append(p)
    return filtered


async def _run_checks(
    entry: BibEntry,
    providers: list[BaseProvider],
) -> tuple[list[ProviderCheckResult], list[str]]:
    """Run checks against providers, return (checks, errors)."""
    tasks = [_check_entry_against_provider(entry, p) for p in providers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    checks: list[ProviderCheckResult] = []
    for provider, result in zip(providers, results, strict=False):
        if isinstance(result, ProviderCheckResult):
            checks.append(result)
        elif isinstance(result, Exception):
            checks.append(
                ProviderCheckResult(
                    provider=provider.provider_name,
                    errors=[f"{provider.provider_name}: {result}"],
                )
            )
    return checks, []


async def verify_entry(
    entry: BibEntry,
    providers: list[BaseProvider],
    config: Config,
) -> VerifyResult:
    """Verify a single entry against providers, with entry-type routing."""
    category = classify_entry_type(entry.entry_type)
    meta = {"entry_type": entry.entry_type, "category": category.value}

    # Non-searchable entries: check for DOI/URL only, skip API queries
    if category == EntryCategory.NON_SEARCHABLE:
        has_doi = bool(entry.doi)
        has_url = bool(entry.fields.get("url"))
        if has_doi or has_url:
            return VerifyResult(
                key=entry.key,
                verdict=Verdict.VERIFIED,
                reasons=[
                    f"{entry.entry_type} entry with {'DOI' if has_doi else 'URL'}"
                ],
                **meta,
            )
        return VerifyResult(
            key=entry.key,
            verdict=Verdict.UNVERIFIED,
            reasons=[f"{entry.entry_type} entry — consider adding a URL or DOI"],
            **meta,
        )

    # Filter providers for this entry's category
    eligible = _filter_providers(entry, providers, category)
    if not eligible:
        return VerifyResult(
            key=entry.key,
            verdict=Verdict.ERROR,
            reasons=["No providers available for this entry type"],
            **meta,
        )

    # Early termination: if entry has DOI, try fast providers first
    fast = [p for p in eligible if p.min_delay_seconds <= 0.1]
    slow = [p for p in eligible if p.min_delay_seconds > 0.1]

    all_candidates: list[Candidate] = []
    errors: list[str] = []
    successful_queries = 0

    if entry.doi and fast:
        checks, _ = await _run_checks(entry, fast)
        for check in checks:
            all_candidates.extend(check.candidates)
            errors.extend(check.errors)
            if check.had_successful_query:
                successful_queries += 1

        # Check if we already have a verified match — skip slow providers
        if all_candidates:
            deduped = _dedupe_candidates(all_candidates)
            ref_fields = {
                "title": entry.title,
                "authors": entry.authors,
                "year": entry.year,
                "venue": entry.venue,
            }
            ranked = _rank_candidates(ref_fields, deduped)
            if ranked[0][0] >= config.verified_threshold:
                return _build_result(entry, ranked, config, **meta)

        # Not verified yet — query slow providers too
        remaining = slow
    else:
        # No DOI or no fast providers — query all at once
        remaining = eligible

    if remaining:
        checks, _ = await _run_checks(entry, remaining)
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
                **meta,
            )

        if category == EntryCategory.BOOK:
            reasons = ["Book not found in CrossRef or OpenAlex"]
        else:
            reasons = ["Not found in any database"]
        reasons.extend(errors[:2])
        return VerifyResult(
            key=entry.key,
            verdict=Verdict.UNVERIFIED,
            reasons=reasons,
            **meta,
        )

    # Score and rank candidates
    ref_fields = {
        "title": entry.title,
        "authors": entry.authors,
        "year": entry.year,
        "venue": entry.venue,
    }
    ranked_candidates = _rank_candidates(ref_fields, all_candidates)
    return _build_result(entry, ranked_candidates, config, **meta)


def _build_result(
    entry: BibEntry,
    ranked_candidates: list[tuple[float, Candidate]],
    config: Config,
    **meta: str,
) -> VerifyResult:
    """Build a VerifyResult from ranked candidates."""
    best_score, best_candidate = ranked_candidates[0]
    scored_candidates = [candidate for _, candidate in ranked_candidates]

    if best_score >= config.verified_threshold:
        verdict = Verdict.VERIFIED
        reasons = [f"Matched with score {best_score:.2f}"]
    elif best_score >= config.likely_threshold:
        verdict = Verdict.LIKELY
        reasons = [f"Likely match with score {best_score:.2f}"]
    else:
        verdict = Verdict.UNVERIFIED
        reasons = [f"Best score {best_score:.2f} below threshold"]

    patch: dict[str, str] = {}
    if best_candidate and verdict in (Verdict.VERIFIED, Verdict.LIKELY):
        if best_candidate.ids.get("doi") and not entry.doi:
            patch["doi"] = best_candidate.ids["doi"]
        elif best_candidate.url and not entry.doi:
            patch["url"] = best_candidate.url

    return VerifyResult(
        key=entry.key,
        verdict=verdict,
        score=best_score,
        reasons=reasons,
        candidates=scored_candidates[:5],
        patch=patch,
        **meta,
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

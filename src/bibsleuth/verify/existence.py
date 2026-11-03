"""Concurrent multi-database citation existence verification."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field

from ..config import Config
from ..parse.extract_ids import extract_ids
from ..parse.normalize import normalize_title
from ..providers.base import BaseProvider, ProviderError
from ..types import (
    BibEntry,
    Candidate,
    EntryCategory,
    Verdict,
    VerifyResult,
    classify_entry_type,
)
from .scoring import score_candidate, title_similarity


@dataclass
class ProviderCheckResult:
    provider: str
    candidates: list[Candidate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    had_successful_query: bool = False


async def _check_entry_against_provider(
    entry: BibEntry,
    provider: BaseProvider,
    request_semaphore: asyncio.Semaphore | None = None,
) -> ProviderCheckResult:
    """Query a single provider for a single entry."""
    result = ProviderCheckResult(provider=provider.provider_name)

    # Try ID-based lookup first
    ids = _entry_identifiers(entry)

    for id_type, identifier in ids.items():
        try:
            if request_semaphore:
                async with request_semaphore:
                    candidates = await provider.lookup_by_id(identifier, id_type)
            else:
                candidates = await provider.lookup_by_id(identifier, id_type)
            result.had_successful_query = True
            result.candidates.extend(candidates)
        except ProviderError as exc:
            result.errors.append(f"{provider.provider_name}: {exc}")

    # Fall back to title search
    if not result.candidates and entry.title:
        try:
            year = int(entry.year) if entry.year else None
            if request_semaphore:
                async with request_semaphore:
                    candidates = await provider.search(
                        title=entry.title,
                        authors=entry.authors[:1] if entry.authors else None,
                        year=year,
                    )
            else:
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
    ids = _entry_identifiers(entry)

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
    request_semaphore: asyncio.Semaphore | None = None,
) -> tuple[list[ProviderCheckResult], list[str]]:
    """Run checks against providers, return (checks, errors)."""
    tasks = [
        _check_entry_against_provider(entry, p, request_semaphore) for p in providers
    ]
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
    request_semaphore: asyncio.Semaphore | None = None,
) -> VerifyResult:
    """Verify a single entry against providers, with entry-type routing."""
    if request_semaphore is None:
        request_semaphore = asyncio.Semaphore(max(1, config.max_concurrent_providers))
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
        checks, _ = await _run_checks(entry, fast, request_semaphore)
        for check in checks:
            all_candidates.extend(check.candidates)
            errors.extend(check.errors)
            if check.had_successful_query:
                successful_queries += 1

        # Check if we already have a verified match — skip slow providers
        if all_candidates:
            deduped = _dedupe_candidates(all_candidates)
            ranked = _rank_candidates(entry, deduped)
            if ranked[0][0] >= config.verified_threshold:
                return _build_result(entry, ranked, config, **meta)

        # Not verified yet — query slow providers too
        remaining = slow
    else:
        # No DOI or no fast providers — query all at once
        remaining = eligible

    if remaining:
        checks, _ = await _run_checks(entry, remaining, request_semaphore)
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
    ranked_candidates = _rank_candidates(entry, all_candidates)
    return _build_result(entry, ranked_candidates, config, **meta)


def _same_main_title(title_a: str, title_b: str) -> bool:
    """True when the titles match before any subtitle (e.g., one source drops it)."""
    main_a = normalize_title(title_a.split(":", 1)[0])
    main_b = normalize_title(title_b.split(":", 1)[0])
    return bool(main_a) and main_a == main_b


def _build_result(
    entry: BibEntry,
    ranked_candidates: list[tuple[float, Candidate]],
    config: Config,
    **meta: str,
) -> VerifyResult:
    """Build a VerifyResult from ranked candidates."""
    best_score, best_candidate = ranked_candidates[0]
    scored_candidates = [candidate for _, candidate in ranked_candidates]

    matching_id = _matching_identifier(entry, best_candidate)
    title_conflict = bool(
        matching_id
        and entry.title
        and best_candidate.title
        and title_similarity(entry.title, best_candidate.title) < 0.5
        and not _same_main_title(entry.title, best_candidate.title)
    )

    if title_conflict:
        verdict = Verdict.CONFLICT
        reasons = [f"Exact {matching_id.upper()} resolves to a conflicting title"]
    elif best_score >= config.verified_threshold:
        verdict = Verdict.VERIFIED
        reasons = (
            [f"Matched exact {matching_id.upper()}"]
            if matching_id
            else [f"Matched with score {best_score:.2f}"]
        )
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
    """Verify entries with bounded task and provider-request concurrency."""
    if not entries:
        return []

    limit = max(1, config.max_concurrent_providers)
    request_semaphore = asyncio.Semaphore(limit)
    work = iter(enumerate(entries))
    results: list[VerifyResult | None] = [None] * len(entries)

    async def worker() -> None:
        for index, entry in work:
            results[index] = await verify_entry(
                entry,
                providers,
                config,
                request_semaphore=request_semaphore,
            )

    workers = [asyncio.create_task(worker()) for _ in range(min(limit, len(entries)))]
    await asyncio.gather(*workers)
    return [result for result in results if result is not None]


def _rank_candidates(
    entry: BibEntry,
    candidates: list[Candidate],
) -> list[tuple[float, Candidate]]:
    ref_fields = {
        "title": entry.title,
        "authors": entry.authors,
        "year": entry.year,
        "venue": entry.venue,
    }
    ranked: list[tuple[float, Candidate]] = []
    for candidate in candidates:
        cand_fields = {
            "title": candidate.title or "",
            "authors": candidate.authors,
            "year": candidate.year,
            "venue": candidate.venue or "",
        }
        score, _ = score_candidate(ref_fields, cand_fields)
        if _matching_identifier(entry, candidate):
            score = 1.0
        ranked.append((score, candidate))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked


def _matching_identifier(entry: BibEntry, candidate: Candidate) -> str | None:
    entry_ids = _entry_identifiers(entry)

    for id_type, entry_value in entry_ids.items():
        candidate_value = candidate.ids.get(id_type)
        if not candidate_value:
            continue
        if _normalize_identifier(id_type, entry_value) == _normalize_identifier(
            id_type, candidate_value
        ):
            return id_type
    return None


def _entry_identifiers(entry: BibEntry) -> dict[str, str]:
    identifiers = extract_ids(entry.raw or "")
    if entry.doi:
        identifiers["doi"] = entry.doi
    return {
        id_type: _normalize_identifier(id_type, identifier)
        for id_type, identifier in identifiers.items()
    }


def _normalize_identifier(id_type: str, value: str) -> str:
    normalized = str(value).strip().lower()
    if id_type == "doi":
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :]
                break
        return normalized.rstrip('.,;:()[]{}<>"')
    if id_type == "arxiv":
        return normalized.removeprefix("arxiv:")
    if id_type == "isbn":
        return re.sub(r"[^0-9x]", "", normalized)
    return normalized


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

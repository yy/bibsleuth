"""High-level LLM analysis pipeline for citation contexts and claims."""

from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Iterable, TypeVar

from ..config import Config
from ..providers.base import BaseProvider, ProviderError
from ..types import (
    BibEntry,
    Candidate,
    CitingContext,
    ClaimContext,
    LLMAnalysis,
    Verdict,
    VerifyResult,
)
from ..verify.existence import verify_entry
from .contradictions import find_contradictions
from .miscitation import check_miscitation
from .suggestions import suggest_citations

T = TypeVar("T")


async def run_llm_analyses(
    contexts: list[CitingContext],
    claims: list[ClaimContext],
    verify_results: list[VerifyResult],
    providers: list[BaseProvider],
    config: Config,
    section: str | None = None,
    uncited_only: bool = False,
) -> list[LLMAnalysis]:
    """Run LLM-powered analyses for cited and uncited claims."""
    analyses: list[LLMAnalysis] = []
    result_by_key = {result.key: result for result in verify_results}
    providers_by_name = {provider.provider_name: provider for provider in providers}

    selected_contexts = [
        context for context in contexts if _section_matches(context.section, section)
    ]
    citation_limit = max(0, config.max_llm_citations)
    omitted_citations = max(0, len(selected_contexts) - citation_limit)
    selected_contexts = selected_contexts[:citation_limit]
    miscitation_tasks = [
        _run_miscitation(context, result_by_key, providers_by_name, config)
        for context in selected_contexts
    ]
    for analysis in await _gather_present(
        miscitation_tasks,
        max_concurrency=config.max_concurrent_llm,
    ):
        analyses.append(analysis)

    if omitted_citations:
        analyses.append(
            LLMAnalysis(
                key="",
                analysis_type="citation_limit",
                status="skipped",
                error=(
                    f"Skipped {omitted_citations} cited contexts due to "
                    "max_llm_citations limit"
                ),
            )
        )

    selected_claims = [
        claim
        for claim in claims
        if _section_matches(claim.section, section)
        and (not uncited_only or not claim.cited_keys)
        and _should_analyze_claim(claim.sentence)
    ]
    claim_limit = max(0, config.max_llm_claims)
    omitted_claims = max(0, len(selected_claims) - claim_limit)
    selected_claims = selected_claims[:claim_limit]
    claim_tasks = [
        _run_claim_analyses(claim, providers, config) for claim in selected_claims
    ]
    for claim_results in await _gather_present(
        claim_tasks,
        max_concurrency=config.max_concurrent_llm,
    ):
        analyses.extend(claim_results)

    if omitted_claims:
        analyses.append(
            LLMAnalysis(
                key="",
                analysis_type="claim_limit",
                status="skipped",
                error=f"Skipped {omitted_claims} claims due to max_llm_claims limit",
            )
        )

    return analyses


async def _run_miscitation(
    context: CitingContext,
    result_by_key: dict[str, VerifyResult],
    providers_by_name: dict[str, BaseProvider],
    config: Config,
) -> LLMAnalysis:
    result = result_by_key.get(context.key)
    if not result:
        return _miscitation_status(context, "skipped", "No verification result")
    if result.verdict not in {Verdict.VERIFIED, Verdict.LIKELY}:
        return _miscitation_status(
            context,
            "skipped",
            f"Citation verification verdict is {result.verdict.value}",
        )
    if not result.candidates:
        return _miscitation_status(context, "skipped", "No matched candidate")

    try:
        abstract = await _find_abstract(result.candidates, providers_by_name)
        if not abstract:
            return _miscitation_status(context, "skipped", "No abstract available")
        return await check_miscitation(context, abstract, config)
    except ImportError:
        raise
    except Exception as exc:
        return _miscitation_status(context, "failed", str(exc))


def _miscitation_status(
    context: CitingContext,
    status: str,
    error: str,
) -> LLMAnalysis:
    return LLMAnalysis(
        key=context.key,
        analysis_type="miscitation",
        status=status,
        error=error,
        claim=context.sentence,
        section=context.section,
    )


async def _find_abstract(
    candidates: list[Candidate],
    providers_by_name: dict[str, BaseProvider],
) -> str | None:
    """Find or enrich an abstract for a verified candidate."""
    for candidate in candidates:
        abstract = await _fetch_abstract(candidate, providers_by_name)
        if abstract:
            return abstract

    identifiers: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        for id_type, identifier in candidate.ids.items():
            item = (id_type, identifier)
            if item not in seen:
                seen.add(item)
                identifiers.append(item)

    for id_type, identifier in identifiers:
        for provider in providers_by_name.values():
            try:
                enriched_candidates = await provider.lookup_by_id(identifier, id_type)
            except ProviderError:
                continue
            for candidate in enriched_candidates:
                abstract = await _fetch_abstract(candidate, providers_by_name)
                if abstract:
                    return abstract
    return None


async def _fetch_abstract(
    candidate: Candidate,
    providers_by_name: dict[str, BaseProvider],
) -> str | None:
    if candidate.abstract:
        return candidate.abstract
    provider = providers_by_name.get(candidate.provider)
    if not provider:
        return None
    try:
        return await provider.fetch_abstract(candidate)
    except ProviderError:
        return None


async def _run_claim_analyses(
    claim: ClaimContext,
    providers: list[BaseProvider],
    config: Config,
) -> list[LLMAnalysis]:
    calls = [
        suggest_citations(claim.sentence, claim.section or claim.sentence, config),
        find_contradictions(
            claim.sentence,
            claim.section or claim.sentence,
            config,
        ),
    ]
    raw_results: list[LLMAnalysis | Exception] = []
    for call in calls:
        try:
            raw_results.append(await call)
        except Exception as exc:
            raw_results.append(exc)

    labels = ("suggestions", "contradictions")
    normalized_results: list[LLMAnalysis] = []
    for label, result in zip(labels, raw_results, strict=True):
        if isinstance(result, ImportError):
            raise result
        if isinstance(result, Exception):
            normalized_results.append(
                LLMAnalysis(
                    key="",
                    analysis_type=label,
                    status="failed",
                    error=str(result),
                    claim=claim.sentence,
                    section=claim.section,
                )
            )
        else:
            result.claim = claim.sentence
            result.section = claim.section
            normalized_results.append(result)

    suggestion_result, contradiction_result = normalized_results

    if suggestion_result.status == "completed":
        try:
            suggestion_result.suggested_papers = await _verify_llm_papers(
                suggestion_result.suggested_papers,
                providers,
                config,
            )
        except Exception as exc:
            suggestion_result.status = "failed"
            suggestion_result.error = f"Paper verification failed: {exc}"
    if contradiction_result.status == "completed":
        try:
            contradiction_result.contradictions = await _verify_llm_papers(
                contradiction_result.contradictions,
                providers,
                config,
            )
        except Exception as exc:
            contradiction_result.status = "failed"
            contradiction_result.error = f"Paper verification failed: {exc}"
    return [suggestion_result, contradiction_result]


async def _verify_llm_papers(
    papers: list[dict],
    providers: list[BaseProvider],
    config: Config,
) -> list[dict]:
    request_semaphore = asyncio.Semaphore(max(1, config.max_concurrent_providers))
    verified = await _gather_present(
        [
            _verify_llm_paper(
                paper,
                providers,
                config,
                request_semaphore=request_semaphore,
            )
            for paper in papers
            if paper.get("title")
        ],
        max_concurrency=config.max_concurrent_providers,
    )
    return verified


async def _verify_llm_paper(
    paper: dict,
    providers: list[BaseProvider],
    config: Config,
    request_semaphore: asyncio.Semaphore | None = None,
) -> dict | None:
    fields = {"title": str(paper.get("title", ""))}
    authors = [str(author) for author in paper.get("authors", []) if author]
    if authors:
        fields["author"] = " and ".join(authors)
    if paper.get("year"):
        fields["year"] = str(paper["year"])

    entry = BibEntry(
        key=str(paper.get("title", "")),
        entry_type="article",
        fields=fields,
        raw=json.dumps(paper),
    )
    result = await verify_entry(
        entry,
        providers,
        config,
        request_semaphore=request_semaphore,
    )
    if result.verdict not in {Verdict.VERIFIED, Verdict.LIKELY}:
        return None

    verified = dict(paper)
    verified["verification"] = {
        "verdict": result.verdict.value,
        "score": round(result.score, 3),
    }
    if result.candidates:
        candidate = result.candidates[0]
        if candidate.url:
            verified["url"] = candidate.url
        if candidate.ids:
            verified["ids"] = candidate.ids
    return verified


async def _gather_present(
    tasks: Iterable[Awaitable[T]],
    max_concurrency: int | None = None,
) -> list[T]:
    task_list = list(tasks)
    if not task_list:
        return []
    if max_concurrency is None:
        results = await asyncio.gather(*task_list)
        return [result for result in results if result is not None]

    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def run(task: Awaitable[T]) -> T:
        async with semaphore:
            return await task

    results = await asyncio.gather(*(run(task) for task in task_list))
    return [result for result in results if result is not None]


def _section_matches(section_name: str, section_filter: str | None) -> bool:
    if not section_filter:
        return True
    normalized_name = " ".join(section_name.lower().split())
    normalized_filter = " ".join(section_filter.lower().split())
    return normalized_filter in normalized_name


def _should_analyze_claim(sentence: str) -> bool:
    stripped = sentence.strip()
    return len(stripped) >= 20 and not stripped.startswith("\\")

"""High-level LLM analysis pipeline for citation contexts and claims."""

from __future__ import annotations

import asyncio
import json
from typing import Iterable

from ..config import Config
from ..providers.base import BaseProvider
from ..types import (
    BibEntry,
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

    miscitation_tasks = [
        _run_miscitation(context, result_by_key, providers_by_name, config)
        for context in contexts
        if _section_matches(context.section, section)
    ]
    for analysis in await _gather_present(miscitation_tasks):
        analyses.append(analysis)

    selected_claims = [
        claim
        for claim in claims
        if _section_matches(claim.section, section)
        and (not uncited_only or not claim.cited_keys)
        and _should_analyze_claim(claim.sentence)
    ]
    claim_tasks = [
        _run_claim_analyses(claim, providers, config)
        for claim in selected_claims
    ]
    for claim_results in await _gather_present(claim_tasks):
        analyses.extend(claim_results)

    return analyses


async def _run_miscitation(
    context: CitingContext,
    result_by_key: dict[str, VerifyResult],
    providers_by_name: dict[str, BaseProvider],
    config: Config,
) -> LLMAnalysis | None:
    result = result_by_key.get(context.key)
    if not result or result.verdict not in {Verdict.VERIFIED, Verdict.LIKELY}:
        return None
    if not result.candidates:
        return None

    candidate = result.candidates[0]
    abstract = candidate.abstract
    if not abstract:
        provider = providers_by_name.get(candidate.provider)
        if provider:
            abstract = await provider.fetch_abstract(candidate)
    if not abstract:
        return None

    return await check_miscitation(context, abstract, config)


async def _run_claim_analyses(
    claim: ClaimContext,
    providers: list[BaseProvider],
    config: Config,
) -> list[LLMAnalysis]:
    suggestion_result, contradiction_result = await _gather_present(
        [
            suggest_citations(claim.sentence, claim.section or claim.sentence, config),
            find_contradictions(
                claim.sentence,
                claim.section or claim.sentence,
                config,
            ),
        ]
    )

    suggestion_result.claim = claim.sentence
    suggestion_result.section = claim.section
    contradiction_result.claim = claim.sentence
    contradiction_result.section = claim.section

    suggestion_result.suggested_papers = await _verify_llm_papers(
        suggestion_result.suggested_papers,
        providers,
        config,
    )
    contradiction_result.contradictions = await _verify_llm_papers(
        contradiction_result.contradictions,
        providers,
        config,
    )
    return [suggestion_result, contradiction_result]


async def _verify_llm_papers(
    papers: list[dict],
    providers: list[BaseProvider],
    config: Config,
) -> list[dict]:
    verified = await _gather_present(
        [
            _verify_llm_paper(paper, providers, config)
            for paper in papers
            if paper.get("title")
        ]
    )
    return verified


async def _verify_llm_paper(
    paper: dict,
    providers: list[BaseProvider],
    config: Config,
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
    result = await verify_entry(entry, providers, config)
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


async def _gather_present(tasks: Iterable) -> list:
    results = await asyncio.gather(*tasks)
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

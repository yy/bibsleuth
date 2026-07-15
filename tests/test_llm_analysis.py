"""Tests for LLM orchestration behavior."""

import asyncio

from bibsleuth.config import Config
from bibsleuth.llm import analysis as analysis_module
from bibsleuth.types import (
    Candidate,
    CitingContext,
    ClaimContext,
    LLMAnalysis,
    Verdict,
    VerifyResult,
)


def test_miscitation_fetches_abstract_from_another_provider(monkeypatch):
    doi = "10.1000/example"

    class PrimaryProvider:
        provider_name = "primary"

        async def fetch_abstract(self, candidate):
            return None

        async def lookup_by_id(self, identifier, id_type):
            return []

    class AbstractProvider:
        provider_name = "abstracts"

        async def fetch_abstract(self, candidate):
            return candidate.abstract

        async def lookup_by_id(self, identifier, id_type):
            assert (identifier, id_type) == (doi, "doi")
            return [
                Candidate(
                    provider=self.provider_name,
                    provider_id="paper",
                    abstract="An abstract with supporting evidence.",
                    ids={"doi": doi},
                )
            ]

    async def fake_check_miscitation(context, abstract, config):
        assert abstract == "An abstract with supporting evidence."
        return LLMAnalysis(key=context.key, supported=True)

    monkeypatch.setattr(
        analysis_module,
        "check_miscitation",
        fake_check_miscitation,
    )

    context = CitingContext(key="paper", sentence=r"A claim \cite{paper}.")
    result = VerifyResult(
        key="paper",
        verdict=Verdict.VERIFIED,
        candidates=[
            Candidate(
                provider="primary",
                provider_id="paper",
                ids={"doi": doi},
            )
        ],
    )
    providers = {
        "primary": PrimaryProvider(),
        "abstracts": AbstractProvider(),
    }

    analysis = asyncio.run(
        analysis_module._run_miscitation(
            context,
            {"paper": result},
            providers,
            Config(),
        )
    )

    assert analysis is not None
    assert analysis.supported is True


def test_claim_analysis_preserves_partial_results(monkeypatch):
    async def failing_suggestions(*args, **kwargs):
        raise RuntimeError("model unavailable")

    async def successful_contradictions(*args, **kwargs):
        return LLMAnalysis(
            key="",
            analysis_type="contradictions",
            contradictions=[{"title": "Counterexample"}],
        )

    monkeypatch.setattr(analysis_module, "suggest_citations", failing_suggestions)
    monkeypatch.setattr(
        analysis_module,
        "find_contradictions",
        successful_contradictions,
    )
    monkeypatch.setattr(
        analysis_module,
        "_verify_llm_papers",
        lambda papers, providers, config: asyncio.sleep(0, result=papers),
    )

    results = asyncio.run(
        analysis_module._run_claim_analyses(
            ClaimContext(sentence="A sufficiently long research claim."),
            [],
            Config(),
        )
    )

    assert results[0].status == "failed"
    assert results[0].error == "model unavailable"
    assert results[1].status == "completed"
    assert results[1].contradictions == [{"title": "Counterexample"}]


def test_llm_claim_limit_is_reported(monkeypatch):
    async def fake_claim_analysis(claim, providers, config):
        return [LLMAnalysis(key="", analysis_type="suggestions", claim=claim.sentence)]

    monkeypatch.setattr(
        analysis_module,
        "_run_claim_analyses",
        fake_claim_analysis,
    )
    claims = [
        ClaimContext(sentence=f"This is sufficiently long claim number {index}.")
        for index in range(3)
    ]

    results = asyncio.run(
        analysis_module.run_llm_analyses(
            [],
            claims,
            [],
            [],
            Config(max_llm_claims=1),
        )
    )

    suggestion_results = [
        result for result in results if result.analysis_type == "suggestions"
    ]
    assert len(suggestion_results) == 1
    limit_result = next(
        result for result in results if result.analysis_type == "claim_limit"
    )
    assert limit_result.status == "skipped"
    assert "Skipped 2 claims" in limit_result.error


def test_gather_present_bounds_concurrency():
    active = 0
    max_active = 0

    async def work(index):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return index

    results = asyncio.run(
        analysis_module._gather_present(
            [work(index) for index in range(8)],
            max_concurrency=2,
        )
    )

    assert results == list(range(8))
    assert max_active == 2


def test_llm_citation_limit_is_reported():
    contexts = [
        CitingContext(key=f"paper-{index}", sentence="A cited research claim.")
        for index in range(3)
    ]

    results = asyncio.run(
        analysis_module.run_llm_analyses(
            contexts,
            [],
            [],
            [],
            Config(max_llm_citations=1),
        )
    )

    miscitation_results = [
        result for result in results if result.analysis_type == "miscitation"
    ]
    assert len(miscitation_results) == 1
    limit_result = next(
        result for result in results if result.analysis_type == "citation_limit"
    )
    assert "Skipped 2 cited contexts" in limit_result.error

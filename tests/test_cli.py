"""Tests for CLI behavior."""

from __future__ import annotations

import argparse

from bibsleuth import cli
from bibsleuth.types import (
    BibEntry,
    CitingContext,
    ClaimContext,
    LLMAnalysis,
    Verdict,
    VerifyResult,
)


class FakeProvider:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeConfig:
    cache_path = "~/.cache/bibsleuth/test.db"
    library_path = "~/.bibsleuth/library.bib"
    positive_ttl_days = 7
    negative_ttl_days = 1
    user_agent = "bibsleuth/test"
    llm_model = "test-model"
    max_concurrent_providers = 6
    verified_threshold = 0.85
    likely_threshold = 0.7
    timeout_seconds = 10.0
    max_retries = 2
    providers = ["fake"]
    openalex_email = None
    s2_api_key = None
    ncbi_api_key = None


def test_run_check_executes_llm_analysis(monkeypatch, tmp_path):
    tex_path = tmp_path / "paper.tex"
    bib_path = tmp_path / "refs.bib"
    tex_path.write_text("\\section{Methods}\nClaim \\cite{demo}.\n", encoding="utf-8")
    bib_path.write_text("@article{demo, title={Demo}}\n", encoding="utf-8")

    llm_calls = {}

    monkeypatch.setattr(cli, "Config", FakeConfig)
    monkeypatch.setattr(cli, "find_bib_path", lambda path: bib_path)
    monkeypatch.setattr(
        cli,
        "parse_bib",
        lambda path: [
            BibEntry(key="demo", entry_type="article", fields={"title": "Demo"})
        ],
    )
    monkeypatch.setattr(
        cli,
        "extract_citations",
        lambda path: [
            CitingContext(
                key="demo",
                sentence="Claim \\cite{demo}.",
                section="Methods",
            )
        ],
    )
    monkeypatch.setattr(
        cli,
        "extract_claims",
        lambda path: [
            ClaimContext(
                sentence="Uncited claim.",
                section="Methods",
                cited_keys=[],
            )
        ],
    )

    async def fake_verify(entries, providers, config):
        return [VerifyResult(key="demo", verdict=Verdict.VERIFIED, score=1.0)]

    async def fake_llm(
        contexts,
        claims,
        results,
        providers,
        config,
        section=None,
        uncited_only=False,
        llm_model=None,
    ):
        llm_calls["section"] = section
        llm_calls["uncited_only"] = uncited_only
        llm_calls["contexts"] = contexts
        llm_calls["claims"] = claims
        return [
            LLMAnalysis(
                key="demo",
                claim="Claim \\cite{demo}.",
                supported=True,
                explanation="ok",
            )
        ]

    rendered = {}

    def fake_to_json(results, config, llm_results=None):
        rendered["llm_results"] = llm_results
        return '{"ok": true}'

    monkeypatch.setattr(cli, "verify_entries", fake_verify)
    monkeypatch.setattr(cli, "run_llm_analyses", fake_llm)
    monkeypatch.setattr(cli, "to_json", fake_to_json)
    monkeypatch.setattr(
        cli,
        "to_markdown",
        lambda results, config, llm_results=None: "report",
    )
    monkeypatch.setattr(cli, "ALL_PROVIDERS", {"fake": FakeProvider})

    args = argparse.Namespace(
        input=str(tex_path),
        bib=None,
        output=None,
        format="json",
        no_llm=False,
        no_cache=True,
        offline=False,
        providers=None,
        section="Methods",
        uncited_only=True,
        llm_model=None,
    )

    exit_code = cli._run_check(args)

    assert exit_code == 0
    assert llm_calls["section"] == "Methods"
    assert llm_calls["uncited_only"] is True
    assert len(rendered["llm_results"]) == 1


def test_run_check_skips_llm_when_disabled(monkeypatch, tmp_path):
    bib_path = tmp_path / "refs.bib"
    bib_path.write_text("@article{demo, title={Demo}}\n", encoding="utf-8")

    monkeypatch.setattr(cli, "Config", FakeConfig)
    monkeypatch.setattr(
        cli,
        "parse_bib",
        lambda path: [
            BibEntry(key="demo", entry_type="article", fields={"title": "Demo"})
        ],
    )

    async def fake_verify(entries, providers, config):
        return [VerifyResult(key="demo", verdict=Verdict.VERIFIED, score=1.0)]

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("LLM analysis should be skipped")

    monkeypatch.setattr(cli, "verify_entries", fake_verify)
    monkeypatch.setattr(cli, "run_llm_analyses", fail_if_called)
    monkeypatch.setattr(
        cli,
        "to_json",
        lambda results, config, llm_results=None: '{"ok": true}',
    )
    monkeypatch.setattr(cli, "ALL_PROVIDERS", {"fake": FakeProvider})

    args = argparse.Namespace(
        input=str(bib_path),
        bib=None,
        output=None,
        format="json",
        no_llm=True,
        no_cache=True,
        offline=False,
        providers=None,
        section=None,
        uncited_only=False,
        llm_model=None,
    )

    exit_code = cli._run_check(args)

    assert exit_code == 0

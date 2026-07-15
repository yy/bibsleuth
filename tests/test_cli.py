"""Tests for CLI behavior."""

from __future__ import annotations

import argparse

import pytest

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
    max_concurrent_llm = 2
    max_llm_citations = 10
    max_llm_claims = 10
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
    monkeypatch.setattr(cli, "find_bib_paths", lambda path: [bib_path])
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


def test_select_cited_entries_reports_missing_keys():
    entries = [
        BibEntry(key="cited", entry_type="article", fields={"title": "Cited"}),
        BibEntry(key="uncited", entry_type="article", fields={"title": "Uncited"}),
    ]
    contexts = [
        CitingContext(key="cited", sentence=r"Claim \cite{cited}."),
        CitingContext(key="missing", sentence=r"Claim \cite{missing}."),
    ]

    selected, missing_results = cli._select_cited_entries(entries, contexts)

    assert [entry.key for entry in selected] == ["cited"]
    assert [result.key for result in missing_results] == ["missing"]
    assert missing_results[0].verdict == Verdict.ERROR


def test_select_cited_entries_honors_nocite_all():
    entries = [
        BibEntry(key="first", entry_type="article"),
        BibEntry(key="second", entry_type="article"),
    ]
    contexts = [CitingContext(key="*", sentence=r"\nocite{*}", command="nocite")]

    selected, missing_results = cli._select_cited_entries(entries, contexts)

    assert selected == entries
    assert missing_results == []


def test_parse_bibliographies_merges_files(tmp_path):
    first = tmp_path / "first.bib"
    second = tmp_path / "second.bib"
    first.write_text("@article{one, title={One}}\n", encoding="utf-8")
    second.write_text("@article{two, title={Two}}\n", encoding="utf-8")

    entries = cli._parse_bibliographies([first, second])

    assert [entry.key for entry in entries] == ["one", "two"]


def test_parse_bibliographies_rejects_conflicting_keys(tmp_path):
    first = tmp_path / "first.bib"
    second = tmp_path / "second.bib"
    first.write_text("@article{same, title={One}}\n", encoding="utf-8")
    second.write_text("@article{same, title={Two}}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Conflicting bibliography key"):
        cli._parse_bibliographies([first, second])


def test_missing_explicit_bibliography_has_clean_error(tmp_path, capsys):
    tex_path = tmp_path / "paper.tex"
    tex_path.write_text("A paper.\n", encoding="utf-8")
    args = argparse.Namespace(
        input=str(tex_path),
        bib=str(tmp_path / "missing.bib"),
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
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "not found" in captured.err
    assert "Traceback" not in captured.err

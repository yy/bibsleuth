"""Tests for report generation."""

from bibsleuth.report import to_markdown
from bibsleuth.types import Candidate, Verdict, VerifyResult


def test_markdown_uses_best_candidate_link():
    result = VerifyResult(
        key="demo",
        verdict=Verdict.VERIFIED,
        score=0.9,
        reasons=["Matched with score 0.90"],
        candidates=[
            Candidate(provider="test", provider_id="good", title="Good", url="https://good.example"),
            Candidate(provider="test", provider_id="bad", title="Bad", url="https://bad.example"),
        ],
    )

    markdown = to_markdown([result], {})

    assert "https://good.example" in markdown
    assert "https://bad.example" not in markdown

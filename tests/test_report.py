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
            Candidate(
                provider="test",
                provider_id="good",
                title="Good",
                url="https://good.example",
            ),
            Candidate(
                provider="test",
                provider_id="bad",
                title="Bad",
                url="https://bad.example",
            ),
        ],
    )

    markdown = to_markdown([result], {})

    assert "https://good.example" in markdown
    assert "https://bad.example" not in markdown


def test_markdown_groups_by_verdict():
    results = [
        VerifyResult(
            key="a", verdict=Verdict.VERIFIED, entry_type="article", category="academic"
        ),
        VerifyResult(
            key="b", verdict=Verdict.UNVERIFIED, entry_type="book", category="book"
        ),
        VerifyResult(
            key="c",
            verdict=Verdict.UNVERIFIED,
            entry_type="misc",
            category="non_searchable",
        ),
    ]
    md = to_markdown(results, {})
    assert "## Verified (1)" in md
    assert "## Unverified (2)" in md
    assert "Books" in md
    assert "Software/Data/Other" in md


def test_json_includes_entry_type():
    import json

    from bibsleuth.report import to_json

    results = [
        VerifyResult(
            key="a", verdict=Verdict.VERIFIED, entry_type="article", category="academic"
        ),
    ]
    data = json.loads(to_json(results, {}))
    assert data["results"][0]["entry_type"] == "article"
    assert data["results"][0]["category"] == "academic"


def test_markdown_patches_section():
    results = [
        VerifyResult(
            key="x",
            verdict=Verdict.LIKELY,
            entry_type="article",
            category="academic",
            patch={"doi": "10.1234/test"},
        ),
    ]
    md = to_markdown(results, {})
    assert "## Suggested Patches (1)" in md
    assert "`x`" in md

"""Report generation in JSON and Markdown formats."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .types import LLMAnalysis, Report, Verdict, VerifyResult


def _make_report(
    results: list[VerifyResult],
    config: dict,
    llm_results: list[LLMAnalysis] | None = None,
) -> Report:
    return Report(
        version=__version__,
        timestamp=datetime.now(timezone.utc).isoformat(),
        config=config,
        verify_results=results,
        llm_results=llm_results or [],
    )


def to_json(
    results: list[VerifyResult],
    config: dict,
    llm_results: list[LLMAnalysis] | None = None,
) -> str:
    """Generate a JSON report."""
    report = _make_report(results, config, llm_results)

    summary = {}
    for v in Verdict:
        count = sum(1 for r in results if r.verdict == v)
        if count:
            summary[v.value] = count

    data = {
        "version": report.version,
        "timestamp": report.timestamp,
        "config": report.config,
        "summary": summary,
        "results": [
            {
                "key": r.key,
                "verdict": r.verdict.value,
                "entry_type": r.entry_type,
                "category": r.category,
                "score": round(r.score, 3),
                "reasons": r.reasons,
                "candidates": [
                    {
                        "provider": c.provider,
                        "title": c.title,
                        "authors": c.authors,
                        "year": c.year,
                        "url": c.url,
                        "ids": c.ids,
                    }
                    for c in r.candidates[:3]
                ],
                "patch": r.patch,
            }
            for r in results
        ],
        "llm_results": [
            {
                "key": analysis.key,
                "claim": analysis.claim,
                "section": analysis.section,
                "supported": analysis.supported,
                "explanation": analysis.explanation,
                "suggested_papers": analysis.suggested_papers,
                "contradictions": analysis.contradictions,
            }
            for analysis in report.llm_results
        ],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


_VERDICT_ORDER = [
    Verdict.RETRACTED,
    Verdict.ERROR,
    Verdict.UNVERIFIED,
    Verdict.CONFLICT,
    Verdict.LIKELY,
    Verdict.VERIFIED,
]

_CATEGORY_LABELS = {
    "academic": "Academic Papers",
    "book": "Books",
    "non_searchable": "Software/Data/Other",
    "": "Other",
}


def _format_entry_md(r: VerifyResult) -> list[str]:
    """Format a single entry as markdown lines."""
    lines = []
    lines.append(f"- **`{r.key}`**")
    if r.entry_type:
        lines.append(f"  - Type: {r.entry_type}")
    if r.score > 0:
        lines.append(f"  - Score: {r.score:.2f}")
    for reason in r.reasons:
        lines.append(f"  - {reason}")
    if r.candidates:
        best = r.candidates[0]
        if best.url:
            lines.append(f"  - Link: [{best.url}]({best.url})")
    if r.patch:
        for k, v in r.patch.items():
            lines.append(f"  - Suggested `{k}`: {v}")
    return lines


def to_markdown(
    results: list[VerifyResult],
    config: dict,
    llm_results: list[LLMAnalysis] | None = None,
) -> str:
    """Generate a Markdown report grouped by verdict and entry category."""
    lines = ["# bibsleuth Report\n"]

    # Summary table
    summary = {}
    for r in results:
        v = r.verdict.value
        summary[v] = summary.get(v, 0) + 1

    lines.append("## Summary\n")
    lines.append("| Verdict | Count |")
    lines.append("| --- | ---: |")
    for verdict, count in sorted(summary.items()):
        lines.append(f"| {verdict} | {count} |")
    lines.append("")

    # Group by verdict, then by category
    by_verdict: dict[Verdict, list[VerifyResult]] = {}
    for r in results:
        by_verdict.setdefault(r.verdict, []).append(r)

    for verdict in _VERDICT_ORDER:
        group = by_verdict.get(verdict)
        if not group:
            continue

        lines.append(f"## {verdict.value.title()} ({len(group)})\n")

        # Sub-group by category
        by_category: dict[str, list[VerifyResult]] = {}
        for r in group:
            by_category.setdefault(r.category, []).append(r)

        categories = sorted(by_category.keys())
        use_subheadings = len(categories) > 1

        for cat in categories:
            cat_entries = by_category[cat]
            if use_subheadings:
                label = _CATEGORY_LABELS.get(cat, cat or "Other")
                lines.append(f"### {label} ({len(cat_entries)})\n")

            for r in cat_entries:
                lines.extend(_format_entry_md(r))
            lines.append("")

    # Suggested patches summary
    patches = [r for r in results if r.patch]
    if patches:
        lines.append(f"## Suggested Patches ({len(patches)})\n")
        for r in patches:
            for k, v in r.patch.items():
                lines.append(f"- `{r.key}`: add `{k}` = {v}")
        lines.append("")

    if llm_results:
        lines.append("## LLM Analysis\n")
        for analysis in llm_results:
            if analysis.key:
                lines.append(f"### Citation `{analysis.key}`\n")
            else:
                lines.append("### Claim Analysis\n")

            if analysis.section:
                lines.append(f"- **Section**: {analysis.section}")
            if analysis.claim:
                lines.append(f"- **Claim**: {analysis.claim}")
            if analysis.supported is not None:
                status = "supports" if analysis.supported else "does not support"
                lines.append(f"- **Support**: {status}")
            if analysis.explanation:
                lines.append(f"- **Explanation**: {analysis.explanation}")
            for paper in analysis.suggested_papers:
                title = paper.get("title", "Untitled")
                lines.append(f"- **Suggested paper**: {title}")
            for paper in analysis.contradictions:
                title = paper.get("title", "Untitled")
                lines.append(f"- **Contradicting paper**: {title}")
            lines.append("")

    return "\n".join(lines)


def write_reports(
    results: list[VerifyResult],
    config: dict,
    output_path: str | Path,
    llm_results: list[LLMAnalysis] | None = None,
) -> None:
    """Write both JSON and Markdown reports."""
    output_path = Path(output_path)
    json_path = output_path.with_suffix(".json")
    md_path = output_path.with_suffix(".md")

    json_path.write_text(
        to_json(results, config, llm_results=llm_results),
        encoding="utf-8",
    )
    md_path.write_text(
        to_markdown(results, config, llm_results=llm_results),
        encoding="utf-8",
    )

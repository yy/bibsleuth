"""Report generation in JSON and Markdown formats."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .types import Report, Verdict, VerifyResult


def _make_report(results: list[VerifyResult], config: dict) -> Report:
    return Report(
        version=__version__,
        timestamp=datetime.now(timezone.utc).isoformat(),
        config=config,
        verify_results=results,
    )


def to_json(results: list[VerifyResult], config: dict) -> str:
    """Generate a JSON report."""
    report = _make_report(results, config)

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
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


def to_markdown(results: list[VerifyResult], config: dict) -> str:
    """Generate a Markdown report."""
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

    # Entries
    lines.append("## Entries\n")
    for r in results:
        icon = {
            Verdict.VERIFIED: "OK",
            Verdict.LIKELY: "~",
            Verdict.UNVERIFIED: "?",
            Verdict.CONFLICT: "!",
            Verdict.RETRACTED: "!!",
            Verdict.ERROR: "ERR",
        }.get(r.verdict, "?")

        lines.append(f"### [{icon}] `{r.key}`\n")
        lines.append(f"- **Verdict**: {r.verdict.value}")
        lines.append(f"- **Score**: {r.score:.2f}")
        for reason in r.reasons:
            lines.append(f"- {reason}")

        if r.candidates:
            best = r.candidates[0]
            if best.url:
                lines.append(f"- **Link**: [{best.url}]({best.url})")

        if r.patch:
            lines.append("- **Suggested patch**:")
            for k, v in r.patch.items():
                lines.append(f"  - `{k}`: {v}")
        lines.append("")

    return "\n".join(lines)


def write_reports(
    results: list[VerifyResult],
    config: dict,
    output_path: str | Path,
) -> None:
    """Write both JSON and Markdown reports."""
    output_path = Path(output_path)
    json_path = output_path.with_suffix(".json")
    md_path = output_path.with_suffix(".md")

    json_path.write_text(to_json(results, config), encoding="utf-8")
    md_path.write_text(to_markdown(results, config), encoding="utf-8")

"""Command-line interface for bibsleuth."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from . import __version__
from .cache import Cache, NullCache
from .config import Config
from .library import add_to_library, search_library
from .llm.analysis import run_llm_analyses
from .parse.bib import parse_bib
from .parse.tex import (
    TexProjectError,
    extract_citations,
    extract_claims,
    find_bib_paths,
)
from .providers import ALL_PROVIDERS
from .report import to_json, to_markdown, write_reports
from .types import BibEntry, CitingContext, Verdict, VerifyResult
from .verify.existence import verify_entries


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bibsleuth",
        description="Citation verification and analysis for LaTeX papers",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    sub = parser.add_subparsers(dest="command")

    # check command
    check = sub.add_parser("check", help="Verify citations")
    check.add_argument("input", help="Path to .tex or .bib file")
    check.add_argument(
        "--bib",
        help="Path to .bib file, or comma-separated paths (auto-detected from .tex)",
    )
    check.add_argument("--output", "-o", help="Output path (writes .json and .md)")
    check.add_argument("--format", choices=["json", "md", "both"], default="both")
    check.add_argument("--no-llm", action="store_true", help="Skip LLM-based analysis")
    check.add_argument(
        "--llm-model",
        help="LLM model passed to litellm (overrides $BIBSLEUTH_LLM_MODEL). "
        "Examples: claude-sonnet-4-20250514, openai/gpt-4o-mini",
    )
    check.add_argument(
        "--llm-concurrency",
        type=int,
        help="Maximum concurrent LLM analyses",
    )
    check.add_argument(
        "--max-llm-claims",
        type=int,
        help="Maximum claims to analyze for suggestions and contradictions",
    )
    check.add_argument(
        "--max-llm-citations",
        type=int,
        help="Maximum cited contexts to analyze for citation support",
    )
    check.add_argument("--no-cache", action="store_true", help="Disable caching")
    check.add_argument("--offline", action="store_true", help="Use cache only")
    check.add_argument(
        "--providers",
        help="Comma-separated list of providers to use",
    )
    check.add_argument("--section", help="Limit analysis to a section")
    check.add_argument("--uncited-only", action="store_true")

    # library command
    lib = sub.add_parser("library", help="Manage system-wide BibTeX library")
    lib_sub = lib.add_subparsers(dest="lib_command")

    lib_add = lib_sub.add_parser("add", help="Add entries from a .bib file")
    lib_add.add_argument("bib_file", help="Path to .bib file")

    lib_search = lib_sub.add_parser("search", help="Search the library")
    lib_search.add_argument("query", help="Search query")

    return parser


def _select_cited_entries(
    entries: list[BibEntry],
    contexts: list[CitingContext],
) -> tuple[list[BibEntry], list[VerifyResult]]:
    """Select cited bibliography entries and report citation keys that are absent."""
    cited_keys = list(dict.fromkeys(context.key for context in contexts))
    include_all = "*" in cited_keys
    cited_keys = [key for key in cited_keys if key != "*"]
    cited_key_set = set(cited_keys)

    entries_by_key = {entry.key: entry for entry in entries}
    selected = (
        entries
        if include_all
        else [entry for entry in entries if entry.key in cited_key_set]
    )
    missing = [
        VerifyResult(
            key=key,
            verdict=Verdict.ERROR,
            reasons=["Citation key not found in bibliography"],
        )
        for key in cited_keys
        if key not in entries_by_key
    ]
    return selected, missing


def _parse_bibliographies(paths: list[Path]) -> list[BibEntry]:
    """Parse and merge bibliography files, rejecting conflicting duplicate keys."""
    merged: list[BibEntry] = []
    by_key: dict[str, tuple[BibEntry, Path]] = {}

    for path in paths:
        for entry in parse_bib(path):
            previous = by_key.get(entry.key)
            if previous:
                previous_entry, previous_path = previous
                if (
                    previous_entry.entry_type != entry.entry_type
                    or previous_entry.fields != entry.fields
                ):
                    raise ValueError(
                        f"Conflicting bibliography key '{entry.key}' in "
                        f"{previous_path} and {path}"
                    )
                continue
            by_key[entry.key] = (entry, path)
            merged.append(entry)
    return merged


def _explicit_bib_paths(value: str) -> list[Path]:
    return [Path(item.strip()) for item in value.split(",") if item.strip()]


def _run_check(args: argparse.Namespace) -> int:
    config = Config()
    if getattr(args, "llm_model", None):
        config.llm_model = args.llm_model
    if getattr(args, "llm_concurrency", None) is not None:
        config.max_concurrent_llm = max(1, args.llm_concurrency)
    if getattr(args, "max_llm_claims", None) is not None:
        config.max_llm_claims = max(0, args.max_llm_claims)
    if getattr(args, "max_llm_citations", None) is not None:
        config.max_llm_citations = max(0, args.max_llm_citations)
    input_path = Path(args.input)

    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        return 1

    # Determine bibliography paths
    if args.bib:
        bib_paths = _explicit_bib_paths(args.bib)
    elif input_path.suffix == ".bib":
        bib_paths = [input_path]
    elif input_path.suffix == ".tex":
        try:
            bib_paths = find_bib_paths(input_path)
        except TexProjectError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        if not bib_paths:
            print(
                "Error: could not find .bib file. Use --bib to specify.",
                file=sys.stderr,
            )
            return 1
    else:
        print(f"Error: unsupported file type {input_path.suffix}", file=sys.stderr)
        return 1

    for bib_path in bib_paths:
        if not bib_path.exists():
            print(f"Error: {bib_path} not found", file=sys.stderr)
            return 1
        if not bib_path.is_file():
            print(f"Error: {bib_path} is not a file", file=sys.stderr)
            return 1

    # Parse bibliographies
    try:
        entries = _parse_bibliographies(bib_paths)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Error: could not parse bibliography: {exc}", file=sys.stderr)
        return 1
    if not entries:
        print("No entries found in .bib file", file=sys.stderr)
        return 1
    bib_summary = ", ".join(str(path) for path in bib_paths)
    print(f"Parsed {len(entries)} entries from {bib_summary}")

    # Extract citing contexts if .tex provided
    contexts = []
    entries_to_verify = entries
    citation_errors: list[VerifyResult] = []
    if input_path.suffix == ".tex":
        try:
            contexts = extract_citations(input_path)
        except TexProjectError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Found {len(contexts)} citation commands in {input_path}")
        entries_to_verify, citation_errors = _select_cited_entries(entries, contexts)

    # Set up cache
    cache = (
        NullCache()
        if args.no_cache
        else Cache(
            path=config.cache_path,
            positive_ttl_days=config.positive_ttl_days,
            negative_ttl_days=config.negative_ttl_days,
        )
    )

    # Set up providers
    provider_names = args.providers.split(",") if args.providers else config.providers
    providers = []
    for name in provider_names:
        name = name.strip()
        if name not in ALL_PROVIDERS:
            print(f"Warning: unknown provider '{name}', skipping", file=sys.stderr)
            continue
        cls = ALL_PROVIDERS[name]
        kwargs = {
            "cache": cache,
            "user_agent": config.user_agent,
            "offline": args.offline,
            "timeout_seconds": config.timeout_seconds,
            "max_retries": config.max_retries,
        }
        if name == "openalex" and config.openalex_email:
            kwargs["email"] = config.openalex_email
        elif name == "crossref" and config.openalex_email:
            kwargs["email"] = config.openalex_email
        elif name == "semantic_scholar" and config.s2_api_key:
            kwargs["api_key"] = config.s2_api_key
        elif name == "pubmed" and config.ncbi_api_key:
            kwargs["api_key"] = config.ncbi_api_key
        providers.append(cls(**kwargs))

    if not providers:
        print("Error: no valid providers configured", file=sys.stderr)
        return 1

    print(f"Checking against {len(providers)} providers...")

    # Run verification (and LLM analysis if enabled) in a single event loop
    async def _run_all():
        try:
            verified_results = await verify_entries(
                entries_to_verify,
                providers,
                config,
            )
            results = citation_errors + verified_results
            llm_results = []
            llm_error = None
            if input_path.suffix == ".tex" and not args.no_llm:
                claims = extract_claims(input_path)
                try:
                    llm_results = await run_llm_analyses(
                        contexts,
                        claims,
                        results,
                        providers,
                        config,
                        section=args.section,
                        uncited_only=args.uncited_only,
                    )
                except ImportError as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    llm_error = str(exc)
            return results, llm_results, llm_error
        finally:
            for p in providers:
                if hasattr(p, "close"):
                    await p.close()

    results, llm_results, llm_error = asyncio.run(_run_all())

    # Print summary
    verdicts = {}
    for r in results:
        v = r.verdict.value
        verdicts[v] = verdicts.get(v, 0) + 1

    print("\nResults:")
    for verdict, count in sorted(verdicts.items()):
        print(f"  {verdict}: {count}")

    report_config = {
        "providers": provider_names,
        "offline": args.offline,
        "llm_enabled": bool(input_path.suffix == ".tex" and not args.no_llm),
        "llm_status": (
            "unavailable"
            if llm_error
            else "enabled"
            if input_path.suffix == ".tex" and not args.no_llm
            else "disabled"
        ),
        "llm_error": llm_error,
        "section": args.section,
        "uncited_only": args.uncited_only,
    }

    # Write reports
    output_path = args.output
    if not output_path and args.format == "both":
        output_path = str(input_path.parent / "bibsleuth-report")

    if output_path:
        try:
            written_paths = write_reports(
                results,
                report_config,
                output_path,
                llm_results=llm_results,
                output_format=args.format,
            )
        except OSError as exc:
            print(f"Error: could not write report: {exc}", file=sys.stderr)
            return 1
        written_summary = ", ".join(str(path) for path in written_paths)
        print(f"\nReports written to {written_summary}")
    else:
        fmt = args.format
        if fmt == "json":
            print("\n" + to_json(results, report_config, llm_results=llm_results))
        elif fmt == "md":
            print("\n" + to_markdown(results, report_config, llm_results=llm_results))

    # Return non-zero if any result requires attention
    failing_verdicts = {
        Verdict.UNVERIFIED,
        Verdict.CONFLICT,
        Verdict.RETRACTED,
        Verdict.ERROR,
    }
    if any(r.verdict in failing_verdicts for r in results):
        return 1
    return 0


def _run_library(args: argparse.Namespace) -> int:
    if args.lib_command == "add":
        entries = parse_bib(args.bib_file)
        added = add_to_library(entries)
        print(f"Added {added} new entries to library")
        return 0
    elif args.lib_command == "search":
        results = search_library(args.query)
        if not results:
            print("No matches found")
            return 0
        for entry in results:
            print(f"  {entry.key}: {entry.title}")
            if entry.authors:
                print(f"    Authors: {', '.join(entry.authors)}")
            if entry.year:
                print(f"    Year: {entry.year}")
            print()
        return 0
    else:
        print("Usage: bibsleuth library {add,search}", file=sys.stderr)
        return 1


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "check":
        sys.exit(_run_check(args))
    elif args.command == "library":
        sys.exit(_run_library(args))
    else:
        parser.print_help()
        sys.exit(0)

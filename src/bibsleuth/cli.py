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
from .parse.tex import extract_citations, extract_claims, find_bib_path
from .providers import ALL_PROVIDERS
from .report import to_json, to_markdown, write_reports
from .types import Verdict
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
    check.add_argument("--bib", help="Path to .bib file (auto-detected from .tex)")
    check.add_argument("--output", "-o", help="Output path (writes .json and .md)")
    check.add_argument("--format", choices=["json", "md", "both"], default="both")
    check.add_argument("--no-llm", action="store_true", help="Skip LLM-based analysis")
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


def _run_check(args: argparse.Namespace) -> int:
    config = Config()
    input_path = Path(args.input)

    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        return 1

    # Determine bib path
    if args.bib:
        bib_path = Path(args.bib)
    elif input_path.suffix == ".bib":
        bib_path = input_path
    elif input_path.suffix == ".tex":
        bib_path = find_bib_path(input_path)
        if not bib_path:
            print(
                "Error: could not find .bib file. Use --bib to specify.",
                file=sys.stderr,
            )
            return 1
    else:
        print(f"Error: unsupported file type {input_path.suffix}", file=sys.stderr)
        return 1

    # Parse bib
    entries = parse_bib(bib_path)
    if not entries:
        print("No entries found in .bib file", file=sys.stderr)
        return 1
    print(f"Parsed {len(entries)} entries from {bib_path}")

    # Extract citing contexts if .tex provided
    contexts = []
    if input_path.suffix == ".tex":
        contexts = extract_citations(input_path)
        print(f"Found {len(contexts)} citation commands in {input_path}")

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
            results = await verify_entries(entries, providers, config)
            llm_results = []
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
            return results, llm_results
        finally:
            for p in providers:
                if hasattr(p, "close"):
                    await p.close()

    results, llm_results = asyncio.run(_run_all())

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
        "section": args.section,
        "uncited_only": args.uncited_only,
    }

    # Write reports
    if args.output:
        write_reports(results, report_config, args.output, llm_results=llm_results)
        print(f"\nReports written to {args.output}.json and {args.output}.md")
    else:
        fmt = args.format
        if fmt in ("json", "both"):
            print("\n" + to_json(results, report_config, llm_results=llm_results))
        if fmt in ("md", "both"):
            print("\n" + to_markdown(results, report_config, llm_results=llm_results))

    # Return non-zero if any unverified
    if any(r.verdict in {Verdict.UNVERIFIED, Verdict.ERROR} for r in results):
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

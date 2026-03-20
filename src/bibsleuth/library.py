"""System-wide BibTeX library management at ~/.bibsleuth/library.bib."""

from __future__ import annotations

import os
from pathlib import Path

import bibtexparser

from .types import BibEntry


def _library_path(config_path: str = "~/.bibsleuth/library.bib") -> Path:
    path = Path(os.path.expanduser(config_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_library(config_path: str = "~/.bibsleuth/library.bib") -> list[BibEntry]:
    """Load the system-wide library."""
    path = _library_path(config_path)
    if not path.exists():
        return []

    library = bibtexparser.parse(path.read_text(encoding="utf-8"))
    entries = []
    for entry in library.entries:
        fields = {k: str(v.value) for k, v in entry.fields_dict.items()}
        entries.append(
            BibEntry(key=entry.key, entry_type=entry.entry_type, fields=fields)
        )
    return entries


def add_to_library(
    entries: list[BibEntry],
    config_path: str = "~/.bibsleuth/library.bib",
) -> int:
    """Add entries to the system-wide library. Returns count of new entries added."""
    path = _library_path(config_path)

    existing = load_library(config_path)
    existing_keys = {e.key for e in existing}

    new_entries = [e for e in entries if e.key not in existing_keys]
    if not new_entries:
        return 0

    # Append to file
    with open(path, "a", encoding="utf-8") as f:
        for entry in new_entries:
            f.write(f"\n@{entry.entry_type}{{{entry.key},\n")
            for key, value in entry.fields.items():
                f.write(f"  {key} = {{{value}}},\n")
            f.write("}\n")

    return len(new_entries)


def search_library(
    query: str,
    config_path: str = "~/.bibsleuth/library.bib",
) -> list[BibEntry]:
    """Search the library by title/author/key substring."""
    query_lower = query.lower()
    results = []
    for entry in load_library(config_path):
        searchable = f"{entry.key} {entry.title} {' '.join(entry.authors)}".lower()
        if query_lower in searchable:
            results.append(entry)
    return results

"""BibTeX parsing via bibtexparser (supports both v1 and v2)."""

from __future__ import annotations

from pathlib import Path

import bibtexparser

from ..types import BibEntry

_V2 = hasattr(bibtexparser, "parse_string")


def parse_bib(path: str | Path) -> list[BibEntry]:
    """Parse a .bib file and return structured entries."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")

    if _V2:
        return _parse_v2(text)
    return _parse_v1(text)


def _parse_v2(text: str) -> list[BibEntry]:
    library = bibtexparser.parse_string(text)
    entries = []
    for entry in library.entries:
        fields = {k: str(v.value) for k, v in entry.fields_dict.items()}
        entries.append(
            BibEntry(key=entry.key, entry_type=entry.entry_type, fields=fields)
        )
    return entries


def _parse_v1(text: str) -> list[BibEntry]:
    parser = bibtexparser.bparser.BibTexParser(common_strings=True)
    db = parser.parse(text)
    entries = []
    for entry in db.entries:
        entry_type = entry.pop("ENTRYTYPE", "article")
        key = entry.pop("ID", "")
        entries.append(BibEntry(key=key, entry_type=entry_type, fields=entry))
    return entries

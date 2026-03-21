"""BibTeX parsing via bibtexparser v2."""

from __future__ import annotations

from pathlib import Path

import bibtexparser

from ..types import BibEntry


def parse_bib(path: str | Path) -> list[BibEntry]:
    """Parse a .bib file and return structured entries."""
    path = Path(path)
    library = bibtexparser.parse_string(path.read_text(encoding="utf-8"))
    entries = []
    for entry in library.entries:
        fields = dict(entry.fields_dict)
        # bibtexparser v2 wraps values in Field objects
        clean_fields = {k: str(v.value) for k, v in fields.items()}
        entries.append(
            BibEntry(
                key=entry.key,
                entry_type=entry.entry_type,
                fields=clean_fields,
            )
        )
    return entries

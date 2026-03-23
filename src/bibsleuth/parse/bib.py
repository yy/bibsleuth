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
    raw_entries = _extract_raw_entries(text)

    if _V2:
        return _parse_v2(text, raw_entries)
    return _parse_v1(text, raw_entries)


def _parse_v2(text: str, raw_entries: dict[str, str]) -> list[BibEntry]:
    library = bibtexparser.parse_string(text)
    entries = []
    for entry in library.entries:
        fields = {k: str(v.value) for k, v in entry.fields_dict.items()}
        entries.append(
            BibEntry(
                key=entry.key,
                entry_type=entry.entry_type,
                fields=fields,
                raw=raw_entries.get(
                    entry.key,
                    _raw_fallback(entry.key, entry.entry_type, fields),
                ),
            )
        )
    return entries


def _parse_v1(text: str, raw_entries: dict[str, str]) -> list[BibEntry]:
    parser = bibtexparser.bparser.BibTexParser(common_strings=True)
    db = parser.parse(text)
    entries = []
    for entry in db.entries:
        entry_type = entry.get("ENTRYTYPE", "article")
        key = entry.get("ID", "")
        fields = {
            field: value
            for field, value in entry.items()
            if field not in {"ENTRYTYPE", "ID"}
        }
        entries.append(
            BibEntry(
                key=key,
                entry_type=entry_type,
                fields=fields,
                raw=raw_entries.get(key, _raw_fallback(key, entry_type, fields)),
            )
        )
    return entries


def _extract_raw_entries(text: str) -> dict[str, str]:
    raw_entries: dict[str, str] = {}
    index = 0

    while index < len(text):
        start = text.find("@", index)
        if start < 0:
            break

        cursor = start + 1
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        while cursor < len(text) and (
            text[cursor].isalnum() or text[cursor] in {"_", "-"}
        ):
            cursor += 1
        if cursor >= len(text) or text[cursor] not in "{(":
            index = start + 1
            continue

        open_char = text[cursor]
        close_char = "}" if open_char == "{" else ")"
        depth = 1
        key_chars: list[str] = []
        key: str | None = None
        cursor += 1

        while cursor < len(text):
            char = text[cursor]
            if depth == 1 and key is None:
                if char == ",":
                    key = "".join(key_chars).strip()
                else:
                    key_chars.append(char)

            if char == open_char:
                depth += 1
            elif char == close_char:
                depth -= 1
                if depth == 0:
                    if key:
                        raw_entries[key] = text[start : cursor + 1]
                    index = cursor + 1
                    break
            cursor += 1
        else:
            break

    return raw_entries


def _raw_fallback(key: str, entry_type: str, fields: dict[str, str]) -> str:
    lines = [f"@{entry_type}{{{key},"]
    lines.extend(f"  {field} = {{{value}}}," for field, value in fields.items())
    lines.append("}")
    return "\n".join(lines)

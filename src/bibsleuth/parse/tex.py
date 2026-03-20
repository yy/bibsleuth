"""Extract citation commands and their surrounding context from .tex files."""

from __future__ import annotations

import re
from pathlib import Path

from ..types import CitingContext

# Matches \cite{key}, \citep{k1,k2}, \citet{key}, \autocite{key},
# \parencite{key}, \textcite{key}, and optional [prenote][postnote] args
CITE_RE = re.compile(
    r"\\(cite[tp]?\*?|autocite\*?|[Pp]arencite\*?|[Tt]extcite\*?|nocite)"
    r"(?:\[[^\]]*\]){0,2}"  # optional prenote/postnote
    r"\{([^}]+)\}",
)


def _extract_sentence(text: str, match_start: int, match_end: int) -> str:
    """Extract the sentence containing the citation."""
    # Look backward for sentence boundary
    start = max(0, match_start - 500)
    prefix = text[start:match_start]
    # Find last sentence-ending punctuation
    for i in range(len(prefix) - 1, -1, -1):
        if prefix[i] in ".!?\n\n":
            prefix = prefix[i + 1 :]
            break

    # Look forward for sentence boundary
    end = min(len(text), match_end + 500)
    suffix = text[match_end:end]
    for i, c in enumerate(suffix):
        if c in ".!?\n":
            suffix = suffix[: i + 1]
            break

    return (prefix + text[match_start:match_end] + suffix).strip()


def extract_citations(path: str | Path) -> list[CitingContext]:
    """Extract all citation commands with context from a .tex file."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")

    # Strip comments
    lines = []
    for line in text.split("\n"):
        # Remove everything after unescaped %
        cleaned = re.sub(r"(?<!\\)%.*$", "", line)
        lines.append(cleaned)
    text = "\n".join(lines)

    results = []
    for match in CITE_RE.finditer(text):
        command = match.group(1)
        keys_str = match.group(2)
        sentence = _extract_sentence(text, match.start(), match.end())

        for key in keys_str.split(","):
            key = key.strip()
            if key:
                results.append(
                    CitingContext(
                        key=key,
                        sentence=sentence,
                        command=command,
                    )
                )
    return results


def find_bib_path(tex_path: str | Path) -> Path | None:
    """Find the .bib file referenced by \\bibliography{} or \\addbibresource{}."""
    tex_path = Path(tex_path)
    text = tex_path.read_text(encoding="utf-8")

    for pattern in [
        r"\\bibliography\{([^}]+)\}",
        r"\\addbibresource\{([^}]+)\}",
    ]:
        match = re.search(pattern, text)
        if match:
            bib_name = match.group(1)
            if not bib_name.endswith(".bib"):
                bib_name += ".bib"
            bib_path = tex_path.parent / bib_name
            if bib_path.exists():
                return bib_path
    return None

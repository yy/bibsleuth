"""Extract citation commands and their surrounding context from .tex files."""

from __future__ import annotations

import re
from pathlib import Path

from ..types import CitingContext, ClaimContext

# Matches \cite{key}, \citep{k1,k2}, \citet{key}, \autocite{key},
# \parencite{key}, \textcite{key}, and optional [prenote][postnote] args
CITE_RE = re.compile(
    r"\\(cite[tp]?\*?|autocite\*?|[Pp]arencite\*?|[Tt]extcite\*?|nocite)"
    r"(?:\[[^\]]*\]){0,2}"  # optional prenote/postnote
    r"\{([^}]+)\}",
)
SECTION_RE = re.compile(
    r"\\(?:part|chapter|section|subsection|subsubsection)\*?\{([^}]+)\}"
)
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")


def _strip_tex_comments(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        lines.append(re.sub(r"(?<!\\)%.*$", "", line))
    return "\n".join(lines)


def _clean_text_fragment(text: str) -> str:
    text = SECTION_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _section_offsets(text: str) -> list[tuple[int, str]]:
    return [
        (match.start(), match.group(1).strip()) for match in SECTION_RE.finditer(text)
    ]


def _section_for_offset(
    sections: list[tuple[int, str]],
    offset: int,
    current_index: int,
    current_section: str,
) -> tuple[int, str]:
    while current_index < len(sections) and sections[current_index][0] <= offset:
        current_section = sections[current_index][1]
        current_index += 1
    return current_index, current_section


def _iter_sentences(text: str) -> list[tuple[str, int]]:
    sentences: list[tuple[str, int]] = []
    start = 0
    for match in SENTENCE_BOUNDARY_RE.finditer(text):
        sentence = _clean_text_fragment(text[start : match.start()])
        if sentence:
            sentences.append((sentence, start))
        start = match.end()

    final_sentence = _clean_text_fragment(text[start:])
    if final_sentence:
        sentences.append((final_sentence, start))

    return sentences


def _extract_sentence(text: str, match_start: int, match_end: int) -> str:
    """Extract the sentence containing the citation."""
    # Look backward for sentence boundary
    start = max(0, match_start - 500)
    prefix = text[start:match_start]
    # Find last sentence-ending punctuation or paragraph break
    for i in range(len(prefix) - 1, -1, -1):
        if prefix[i] in ".!?":
            prefix = prefix[i + 1 :]
            break
        if prefix[i] == "\n" and i > 0 and prefix[i - 1] == "\n":
            prefix = prefix[i + 1 :]
            break

    # Look forward for sentence boundary
    end = min(len(text), match_end + 500)
    suffix = text[match_end:end]
    for i, c in enumerate(suffix):
        if c in ".!?":
            suffix = suffix[: i + 1]
            break
        if c == "\n" and i + 1 < len(suffix) and suffix[i + 1] == "\n":
            suffix = suffix[:i]
            break

    return (prefix + text[match_start:match_end] + suffix).strip()


def extract_citations(path: str | Path) -> list[CitingContext]:
    """Extract all citation commands with context from a .tex file."""
    path = Path(path)
    text = _strip_tex_comments(path.read_text(encoding="utf-8"))
    sections = _section_offsets(text)
    section_index = 0
    current_section = ""

    results = []
    for match in CITE_RE.finditer(text):
        section_index, current_section = _section_for_offset(
            sections,
            match.start(),
            section_index,
            current_section,
        )
        command = match.group(1)
        keys_str = match.group(2)
        sentence = _clean_text_fragment(
            _extract_sentence(text, match.start(), match.end())
        )

        for key in keys_str.split(","):
            key = key.strip()
            if key:
                results.append(
                    CitingContext(
                        key=key,
                        sentence=sentence,
                        command=command,
                        section=current_section,
                    )
                )
    return results


def extract_claims(path: str | Path) -> list[ClaimContext]:
    """Extract sentence-level claims and any citation keys they contain."""
    path = Path(path)
    text = _strip_tex_comments(path.read_text(encoding="utf-8"))
    sections = _section_offsets(text)
    section_index = 0
    current_section = ""
    claims: list[ClaimContext] = []

    for sentence, offset in _iter_sentences(text):
        section_index, current_section = _section_for_offset(
            sections,
            offset,
            section_index,
            current_section,
        )
        cited_keys: list[str] = []
        for _, keys_str in CITE_RE.findall(sentence):
            cited_keys.extend(key.strip() for key in keys_str.split(",") if key.strip())
        claims.append(
            ClaimContext(
                sentence=sentence,
                section=current_section,
                cited_keys=cited_keys,
            )
        )

    return claims


def find_bib_path(tex_path: str | Path) -> Path | None:
    """Find the .bib file referenced by \\bibliography{} or \\addbibresource{}."""
    tex_path = Path(tex_path)
    text = _strip_tex_comments(tex_path.read_text(encoding="utf-8"))

    for pattern in [
        r"\\bibliography\{([^}]+)\}",
        r"\\addbibresource\{([^}]+)\}",
    ]:
        for match in re.finditer(pattern, text):
            for bib_name in match.group(1).split(","):
                bib_name = bib_name.strip().strip("\"'")
                if not bib_name:
                    continue
                if not bib_name.endswith(".bib"):
                    bib_name += ".bib"
                bib_path = tex_path.parent / bib_name
                if bib_path.exists():
                    return bib_path
    return None

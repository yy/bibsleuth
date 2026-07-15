"""Core data types for bibsleuth."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


def _split_bibtex_authors(raw: str) -> list[str]:
    """Split a BibTeX author list on unbraced `and` separators."""
    authors: list[str] = []
    depth = 0
    start = 0
    index = 0

    while index < len(raw):
        char = raw[index]
        if char == "{":
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
        elif (
            depth == 0
            and raw[index : index + 3].lower() == "and"
            and (index == 0 or raw[index - 1].isspace())
            and (index + 3 == len(raw) or raw[index + 3].isspace())
        ):
            author = raw[start:index].strip()
            if author:
                authors.append(author)
            start = index + 3
            index += 2
        index += 1

    final_author = raw[start:].strip()
    if final_author:
        authors.append(final_author)
    return authors


class EntryCategory(Enum):
    ACADEMIC = "academic"
    BOOK = "book"
    NON_SEARCHABLE = "non_searchable"


_ENTRY_TYPE_MAP: dict[str, EntryCategory] = {
    "article": EntryCategory.ACADEMIC,
    "inproceedings": EntryCategory.ACADEMIC,
    "conference": EntryCategory.ACADEMIC,
    "proceedings": EntryCategory.ACADEMIC,
    "incollection": EntryCategory.ACADEMIC,
    "phdthesis": EntryCategory.ACADEMIC,
    "mastersthesis": EntryCategory.ACADEMIC,
    "techreport": EntryCategory.ACADEMIC,
    "unpublished": EntryCategory.ACADEMIC,
    "book": EntryCategory.BOOK,
    "inbook": EntryCategory.BOOK,
    "booklet": EntryCategory.BOOK,
    "misc": EntryCategory.NON_SEARCHABLE,
    "software": EntryCategory.NON_SEARCHABLE,
    "dataset": EntryCategory.NON_SEARCHABLE,
    "online": EntryCategory.NON_SEARCHABLE,
    "webpage": EntryCategory.NON_SEARCHABLE,
    "manual": EntryCategory.NON_SEARCHABLE,
    "electronic": EntryCategory.NON_SEARCHABLE,
}


def classify_entry_type(entry_type: str) -> EntryCategory:
    """Classify a BibTeX entry type into a search category."""
    return _ENTRY_TYPE_MAP.get(entry_type.lower(), EntryCategory.ACADEMIC)


class Verdict(Enum):
    VERIFIED = "verified"
    LIKELY = "likely"
    UNVERIFIED = "unverified"
    CONFLICT = "conflict"
    RETRACTED = "retracted"
    ERROR = "error"


@dataclass
class BibEntry:
    """A parsed BibTeX entry."""

    key: str
    entry_type: str
    fields: dict[str, str] = field(default_factory=dict)
    raw: str = ""

    @property
    def title(self) -> str:
        return self.fields.get("title", "")

    @property
    def authors(self) -> list[str]:
        raw = self.fields.get("author", "")
        if not raw:
            return []
        return _split_bibtex_authors(raw)

    @property
    def year(self) -> str | None:
        return self.fields.get("year")

    @property
    def doi(self) -> str | None:
        return self.fields.get("doi")

    @property
    def venue(self) -> str:
        return self.fields.get("journal", "") or self.fields.get("booktitle", "") or ""


@dataclass
class CitingContext:
    """A citation key with its surrounding text from a .tex file."""

    key: str
    sentence: str
    command: str = "cite"  # cite, citep, citet, autocite, etc.
    section: str = ""


@dataclass
class ClaimContext:
    """A sentence-level claim extracted from a .tex file."""

    sentence: str
    section: str = ""
    cited_keys: list[str] = field(default_factory=list)


@dataclass
class Candidate:
    """A candidate match from an academic database."""

    provider: str
    provider_id: str
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    ids: dict[str, str] = field(default_factory=dict)
    url: str | None = None


@dataclass
class VerifyResult:
    """Verification result for a single BibTeX entry."""

    key: str
    verdict: Verdict
    entry_type: str = ""
    category: str = ""
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    patch: dict[str, str] = field(default_factory=dict)


@dataclass
class LLMAnalysis:
    """LLM-based analysis result for a citation."""

    key: str
    analysis_type: str = ""
    status: str = "completed"
    error: str = ""
    claim: str = ""
    section: str = ""
    supported: bool | None = None
    explanation: str = ""
    suggested_papers: list[dict[str, Any]] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Report:
    """Top-level report aggregating all results."""

    version: str
    timestamp: str
    config: dict[str, Any] = field(default_factory=dict)
    verify_results: list[VerifyResult] = field(default_factory=list)
    llm_results: list[LLMAnalysis] = field(default_factory=list)

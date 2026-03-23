"""Core data types for bibsleuth."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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
        return [a.strip() for a in raw.split(" and ")]

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
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    patch: dict[str, str] = field(default_factory=dict)


@dataclass
class LLMAnalysis:
    """LLM-based analysis result for a citation."""

    key: str
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

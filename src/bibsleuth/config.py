"""Configuration for bibsleuth."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    cache_path: str = "~/.cache/bibsleuth/cache.db"
    library_path: str = "~/.bibsleuth/library.bib"
    positive_ttl_days: int = 7
    negative_ttl_days: int = 1
    user_agent: str = "bibsleuth/0.1 (https://github.com/yy/bibsleuth)"
    llm_model: str = "claude-sonnet-4-20250514"
    max_concurrent_providers: int = 6
    verified_threshold: float = 0.85
    likely_threshold: float = 0.70
    timeout_seconds: float = 10.0
    max_retries: int = 2
    providers: list[str] = field(
        default_factory=lambda: [
            "openalex",
            "semantic_scholar",
            "crossref",
            "arxiv",
            "dblp",
            "pubmed",
        ]
    )

    # API keys from environment
    @property
    def openalex_email(self) -> str | None:
        return os.environ.get("OPENALEX_EMAIL")

    @property
    def s2_api_key(self) -> str | None:
        return os.environ.get("SEMANTIC_SCHOLAR_API_KEY")

    @property
    def ncbi_api_key(self) -> str | None:
        return os.environ.get("NCBI_API_KEY")

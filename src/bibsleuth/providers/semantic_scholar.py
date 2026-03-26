"""Semantic Scholar provider (https://api.semanticscholar.org)."""

from __future__ import annotations

from ..types import Candidate
from .base import BaseProvider


class SemanticScholarProvider(BaseProvider):
    provider_name = "semantic_scholar"
    base_url = "https://api.semanticscholar.org/graph/v1"
    supported_categories = frozenset({"academic"})
    min_delay_seconds = 1.0  # 1 req/s without API key

    FIELDS = "title,authors,year,venue,abstract,externalIds,url"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key
        if api_key:
            self.min_delay_seconds = 0.1

    def _headers(self) -> dict[str, str]:
        if self.api_key:
            return {"x-api-key": self.api_key}
        return {}

    async def search(
        self,
        title: str,
        authors: list[str] | None = None,
        year: int | None = None,
    ) -> list[Candidate]:
        query = title
        if authors:
            query += " " + authors[0]

        params = {"query": query, "limit": 5, "fields": self.FIELDS}
        if year:
            params["year"] = str(year)

        resp = await self._request_json(
            f"{self.base_url}/paper/search",
            params=params,
            headers=self._headers(),
        )
        if resp["status_code"] != 200:
            return []

        return [self._parse_paper(p) for p in resp["data"].get("data", [])]

    async def lookup_by_id(self, identifier: str, id_type: str) -> list[Candidate]:
        if id_type == "doi":
            paper_id = f"DOI:{identifier}"
        elif id_type == "arxiv":
            paper_id = f"ARXIV:{identifier}"
        elif id_type == "s2":
            paper_id = identifier
        else:
            return []

        resp = await self._request_json(
            f"{self.base_url}/paper/{paper_id}",
            params={"fields": self.FIELDS},
            headers=self._headers(),
        )
        if resp["status_code"] != 200:
            return []
        return [self._parse_paper(resp["data"])]

    def _parse_paper(self, paper: dict) -> Candidate:
        authors = [a.get("name", "") for a in paper.get("authors", [])]

        ids: dict[str, str] = {}
        ext = paper.get("externalIds", {})
        if ext.get("DOI"):
            ids["doi"] = ext["DOI"]
        if ext.get("ArXiv"):
            ids["arxiv"] = ext["ArXiv"]

        return Candidate(
            provider=self.provider_name,
            provider_id=paper.get("paperId", ""),
            title=paper.get("title"),
            authors=authors,
            year=paper.get("year"),
            venue=paper.get("venue"),
            abstract=paper.get("abstract"),
            ids=ids,
            url=paper.get("url"),
        )

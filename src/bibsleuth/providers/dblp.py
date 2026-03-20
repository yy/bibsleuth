"""DBLP provider (https://dblp.org/search/publ/api)."""

from __future__ import annotations

from ..types import Candidate
from .base import BaseProvider


class DBLPProvider(BaseProvider):
    provider_name = "dblp"
    base_url = "https://dblp.org/search/publ/api"
    min_delay_seconds = 0.7

    async def search(
        self,
        title: str,
        authors: list[str] | None = None,
        year: int | None = None,
    ) -> list[Candidate]:
        query = title
        if authors:
            query += " " + authors[0].split()[-1]

        params = {"q": query, "format": "json", "h": 5}
        resp = await self._request_json(self.base_url, params=params)
        if resp["status_code"] != 200:
            return []

        hits = resp["data"].get("result", {}).get("hits", {}).get("hit", [])
        return [self._parse_hit(h.get("info", {})) for h in hits]

    async def lookup_by_id(self, identifier: str, id_type: str) -> list[Candidate]:
        if id_type != "dblp":
            return []
        # DBLP doesn't have a direct ID lookup API, use search
        return await self.search(identifier)

    def _parse_hit(self, info: dict) -> Candidate:
        authors_data = info.get("authors", {}).get("author", [])
        if isinstance(authors_data, dict):
            authors_data = [authors_data]
        authors = [
            a.get("text", "") if isinstance(a, dict) else str(a) for a in authors_data
        ]

        ids: dict[str, str] = {}
        if info.get("doi"):
            ids["doi"] = info["doi"]

        return Candidate(
            provider=self.provider_name,
            provider_id=info.get("key", ""),
            title=info.get("title"),
            authors=authors,
            year=int(info["year"]) if info.get("year") else None,
            venue=info.get("venue"),
            ids=ids,
            url=info.get("ee") or info.get("url"),
        )

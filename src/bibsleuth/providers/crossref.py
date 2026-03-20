"""CrossRef provider (https://api.crossref.org)."""

from __future__ import annotations

from ..types import Candidate
from .base import BaseProvider


class CrossRefProvider(BaseProvider):
    provider_name = "crossref"
    base_url = "https://api.crossref.org"
    min_delay_seconds = 0.1  # polite pool with mailto

    async def search(
        self,
        title: str,
        authors: list[str] | None = None,
        year: int | None = None,
    ) -> list[Candidate]:
        params: dict = {
            "query.bibliographic": title,
            "rows": 5,
            "mailto": self.user_agent,
        }
        if authors:
            params["query.author"] = authors[0]

        resp = await self._request_json(f"{self.base_url}/works", params=params)
        if resp["status_code"] != 200:
            return []

        items = resp["data"].get("message", {}).get("items", [])
        return [self._parse_item(item) for item in items]

    async def lookup_by_id(self, identifier: str, id_type: str) -> list[Candidate]:
        if id_type != "doi":
            return []

        resp = await self._request_json(
            f"{self.base_url}/works/{identifier}",
            params={"mailto": self.user_agent},
        )
        if resp["status_code"] != 200:
            return []
        return [self._parse_item(resp["data"].get("message", {}))]

    def _parse_item(self, item: dict) -> Candidate:
        authors = []
        for author in item.get("author", []):
            given = author.get("given", "")
            family = author.get("family", "")
            authors.append(f"{given} {family}".strip())

        title_list = item.get("title", [])
        title = title_list[0] if title_list else None

        ids: dict[str, str] = {}
        if item.get("DOI"):
            ids["doi"] = item["DOI"]

        year = None
        date_parts = item.get("published-print", {}).get("date-parts") or item.get(
            "published-online", {}
        ).get("date-parts")
        if date_parts and date_parts[0]:
            year = date_parts[0][0]

        venue = (
            item.get("container-title", [None])[0]
            if item.get("container-title")
            else None
        )

        # Check retraction status
        is_retracted = bool(item.get("update-to")) or bool(item.get("is-retracted-by"))

        return Candidate(
            provider=self.provider_name,
            provider_id=item.get("DOI", ""),
            title=title,
            authors=authors,
            year=year,
            venue=venue,
            ids=ids,
            url=f"https://doi.org/{item['DOI']}" if item.get("DOI") else None,
        )

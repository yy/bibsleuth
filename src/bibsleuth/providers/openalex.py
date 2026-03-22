"""OpenAlex provider (https://docs.openalex.org)."""

from __future__ import annotations

from ..types import Candidate
from .base import BaseProvider


class OpenAlexProvider(BaseProvider):
    provider_name = "openalex"
    base_url = "https://api.openalex.org"
    min_delay_seconds = 0.1  # polite pool: 10 req/s with email

    def __init__(self, email: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.email = email

    async def search(
        self,
        title: str,
        authors: list[str] | None = None,
        year: int | None = None,
    ) -> list[Candidate]:
        params: dict = {"search": title, "per_page": 5}
        if self.email:
            params["mailto"] = self.email
        if year:
            params["filter"] = f"publication_year:{year}"

        resp = await self._request_json(f"{self.base_url}/works", params=params)
        if resp["status_code"] != 200:
            return []

        candidates = []
        for work in resp["data"].get("results", []):
            candidates.append(self._parse_work(work))
        return candidates

    async def lookup_by_id(self, identifier: str, id_type: str) -> list[Candidate]:
        if id_type == "doi":
            url = f"{self.base_url}/works/https://doi.org/{identifier}"
        elif id_type == "openalex":
            url = f"{self.base_url}/works/{identifier}"
        else:
            return []

        params = {"mailto": self.email} if self.email else {}
        resp = await self._request_json(url, params=params)
        if resp["status_code"] != 200:
            return []
        return [self._parse_work(resp["data"])]

    def _parse_work(self, work: dict) -> Candidate:
        authors = []
        for authorship in work.get("authorships", []):
            author = authorship.get("author", {})
            name = author.get("display_name")
            if name:
                authors.append(name)

        ids: dict[str, str] = {}
        if work.get("doi"):
            ids["doi"] = work["doi"].replace("https://doi.org/", "")
        if work.get("ids", {}).get("openalex"):
            ids["openalex"] = work["ids"]["openalex"]

        location = work.get("primary_location") or {}
        source = location.get("source") or {}
        venue = source.get("display_name") if isinstance(source, dict) else None

        return Candidate(
            provider=self.provider_name,
            provider_id=work.get("id", ""),
            title=work.get("title"),
            authors=authors,
            year=work.get("publication_year"),
            venue=venue,
            abstract=work.get("abstract"),
            ids=ids,
            url=work.get("doi") or work.get("id"),
        )

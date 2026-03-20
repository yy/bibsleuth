"""PubMed provider (NCBI E-utilities)."""

from __future__ import annotations

from ..types import Candidate
from .base import BaseProvider


class PubMedProvider(BaseProvider):
    provider_name = "pubmed"
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    min_delay_seconds = 0.35  # ~3 req/s without API key

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key
        if api_key:
            self.min_delay_seconds = 0.1

    async def search(
        self,
        title: str,
        authors: list[str] | None = None,
        year: int | None = None,
    ) -> list[Candidate]:
        query = f"{title}[Title]"
        if authors:
            query += f" AND {authors[0].split()[-1]}[Author]"
        if year:
            query += f" AND {year}[PDAT]"

        params: dict = {"db": "pubmed", "term": query, "retmax": 5, "retmode": "json"}
        if self.api_key:
            params["api_key"] = self.api_key

        resp = await self._request_json(f"{self.base_url}/esearch.fcgi", params=params)
        if resp["status_code"] != 200:
            return []

        id_list = resp["data"].get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return []

        return await self._fetch_details(id_list)

    async def lookup_by_id(self, identifier: str, id_type: str) -> list[Candidate]:
        if id_type != "pmid":
            return []
        return await self._fetch_details([identifier])

    async def _fetch_details(self, pmids: list[str]) -> list[Candidate]:
        params: dict = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "json",
        }
        if self.api_key:
            params["api_key"] = self.api_key

        resp = await self._request_json(f"{self.base_url}/esummary.fcgi", params=params)
        if resp["status_code"] != 200:
            return []

        result = resp["data"].get("result", {})
        candidates = []
        for pmid in pmids:
            doc = result.get(pmid, {})
            if not doc or not isinstance(doc, dict):
                continue

            authors = [a.get("name", "") for a in doc.get("authors", [])]

            ids: dict[str, str] = {"pmid": pmid}
            for aid in doc.get("articleids", []):
                if aid.get("idtype") == "doi":
                    ids["doi"] = aid["value"]

            candidates.append(
                Candidate(
                    provider=self.provider_name,
                    provider_id=pmid,
                    title=doc.get("title"),
                    authors=authors,
                    year=int(doc["pubdate"][:4]) if doc.get("pubdate") else None,
                    venue=doc.get("fulljournalname"),
                    ids=ids,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                )
            )
        return candidates

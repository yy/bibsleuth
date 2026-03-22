"""arXiv provider (https://export.arxiv.org/api)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from ..types import Candidate
from .base import BaseProvider

ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


class ArxivProvider(BaseProvider):
    provider_name = "arxiv"
    base_url = "https://export.arxiv.org/api/query"
    min_delay_seconds = 3.0  # arXiv asks for 3s between requests

    async def search(
        self,
        title: str,
        authors: list[str] | None = None,
        year: int | None = None,
    ) -> list[Candidate]:
        query_parts = [f'ti:"{title}"']
        if authors:
            query_parts.append(f"au:{authors[0].split()[-1]}")

        params = {
            "search_query": " AND ".join(query_parts),
            "max_results": 5,
        }
        resp = await self._request_json(self.base_url, params=params)
        if resp["status_code"] != 200:
            return []

        # arXiv returns XML; base class stores it as {"raw": ...}
        return self._parse_atom(resp["data"].get("raw", ""))

    async def lookup_by_id(self, identifier: str, id_type: str) -> list[Candidate]:
        if id_type != "arxiv":
            return []

        params = {"id_list": identifier}
        resp = await self._request_json(self.base_url, params=params)
        if resp["status_code"] != 200:
            return []

        return self._parse_atom(resp["data"].get("raw", ""))

    def _parse_atom(self, xml_text: str) -> list[Candidate]:
        if not xml_text:
            return []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []

        candidates = []
        for entry in root.findall(f"{ATOM_NS}entry"):
            title_el = entry.find(f"{ATOM_NS}title")
            title = (
                title_el.text.strip()
                if title_el is not None and title_el.text
                else None
            )

            authors = []
            for author_el in entry.findall(f"{ATOM_NS}author"):
                name_el = author_el.find(f"{ATOM_NS}name")
                if name_el is not None and name_el.text:
                    authors.append(name_el.text)

            published = entry.find(f"{ATOM_NS}published")
            year = None
            if published is not None and published.text:
                try:
                    year = int(published.text[:4])
                except (ValueError, IndexError):
                    pass

            abstract_el = entry.find(f"{ATOM_NS}summary")
            abstract = (
                abstract_el.text.strip()
                if abstract_el is not None and abstract_el.text
                else None
            )

            link_el = entry.find(f"{ATOM_NS}id")
            url = link_el.text if link_el is not None else None

            arxiv_id = None
            if url:
                match = re.search(r"(\d{4}\.\d{4,5}|[a-z\-]+/\d{7})", url)
                if match:
                    arxiv_id = match.group(1)

            ids: dict[str, str] = {}
            if arxiv_id:
                ids["arxiv"] = arxiv_id

            doi_el = entry.find(f"{ARXIV_NS}doi")
            if doi_el is not None and doi_el.text:
                ids["doi"] = doi_el.text.strip()

            candidates.append(
                Candidate(
                    provider=self.provider_name,
                    provider_id=arxiv_id or "",
                    title=title,
                    authors=authors,
                    year=year,
                    abstract=abstract,
                    ids=ids,
                    url=url,
                )
            )
        return candidates

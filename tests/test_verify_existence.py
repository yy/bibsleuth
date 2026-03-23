"""Tests for verification behavior."""

import asyncio

from bibsleuth.config import Config
from bibsleuth.providers.base import ProviderError
from bibsleuth.types import BibEntry, Candidate, Verdict
from bibsleuth.verify.existence import verify_entry


class FailingProvider:
    provider_name = "failing"

    async def lookup_by_id(self, identifier: str, id_type: str):
        raise ProviderError("provider unavailable")

    async def search(self, title: str, authors=None, year=None):
        raise ProviderError("provider unavailable")


class RankedProvider:
    provider_name = "ranked"

    async def lookup_by_id(self, identifier: str, id_type: str):
        return []

    async def search(self, title: str, authors=None, year=None):
        return [
            Candidate(
                provider=self.provider_name,
                provider_id="bad",
                title="Completely Different",
                authors=["Other Author"],
                year=1999,
                url="https://bad.example",
            ),
            Candidate(
                provider=self.provider_name,
                provider_id="good",
                title="Exact Match",
                authors=["Alice Smith"],
                year=2024,
                url="https://good.example",
            ),
        ]


def test_verify_entry_returns_error_when_all_providers_fail():
    entry = BibEntry(key="demo", entry_type="article", fields={"title": "Example"})

    result = asyncio.run(verify_entry(entry, [FailingProvider()], Config()))

    assert result.verdict == Verdict.ERROR
    assert "provider unavailable" in result.reasons[0]


def test_verify_entry_sorts_candidates_by_score():
    entry = BibEntry(
        key="demo",
        entry_type="article",
        fields={
            "title": "Exact Match",
            "author": "Alice Smith",
            "year": "2024",
        },
    )
    config = Config(verified_threshold=0.85, likely_threshold=0.7)

    result = asyncio.run(verify_entry(entry, [RankedProvider()], config))

    assert result.verdict == Verdict.VERIFIED
    assert result.candidates[0].provider_id == "good"
    assert result.patch["url"] == "https://good.example"

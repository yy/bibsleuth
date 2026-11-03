"""Tests for verification behavior."""

import asyncio

from bibsleuth.config import Config
from bibsleuth.providers.base import ProviderError
from bibsleuth.types import BibEntry, Candidate, Verdict
from bibsleuth.verify.existence import verify_entries, verify_entry


class FailingProvider:
    provider_name = "failing"
    supported_categories = frozenset({"academic", "book", "non_searchable"})
    min_delay_seconds = 0.0

    async def lookup_by_id(self, identifier: str, id_type: str):
        raise ProviderError("provider unavailable")

    async def search(self, title: str, authors=None, year=None):
        raise ProviderError("provider unavailable")


class RankedProvider:
    provider_name = "ranked"
    supported_categories = frozenset({"academic", "book", "non_searchable"})
    min_delay_seconds = 0.0

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


def test_non_searchable_entry_with_url_verified():
    entry = BibEntry(
        key="foursquare",
        entry_type="misc",
        fields={"title": "Foursquare", "url": "https://foursquare.com"},
    )
    result = asyncio.run(verify_entry(entry, [FailingProvider()], Config()))
    assert result.verdict == Verdict.VERIFIED
    assert result.entry_type == "misc"
    assert result.category == "non_searchable"
    assert "URL" in result.reasons[0]


def test_non_searchable_entry_with_doi_verified():
    entry = BibEntry(
        key="zenodo",
        entry_type="software",
        fields={"title": "My Software", "doi": "10.5281/zenodo.123"},
    )
    result = asyncio.run(verify_entry(entry, [FailingProvider()], Config()))
    assert result.verdict == Verdict.VERIFIED
    assert "DOI" in result.reasons[0]


def test_non_searchable_entry_without_url_unverified():
    entry = BibEntry(
        key="dataset",
        entry_type="misc",
        fields={"title": "Some Dataset"},
    )
    result = asyncio.run(verify_entry(entry, [FailingProvider()], Config()))
    assert result.verdict == Verdict.UNVERIFIED
    assert "consider adding" in result.reasons[0].lower()


def test_book_only_uses_compatible_providers():
    """Book entries should skip academic-only providers."""
    call_log = []

    class AcademicOnly:
        provider_name = "academic_only"
        supported_categories = frozenset({"academic"})
        min_delay_seconds = 0.0

        async def lookup_by_id(self, identifier, id_type):
            call_log.append("academic_only")
            return []

        async def search(self, title, authors=None, year=None):
            call_log.append("academic_only")
            return []

    class BookCompatible:
        provider_name = "book_ok"
        supported_categories = frozenset({"academic", "book"})
        min_delay_seconds = 0.0

        async def lookup_by_id(self, identifier, id_type):
            call_log.append("book_ok")
            return []

        async def search(self, title, authors=None, year=None):
            call_log.append("book_ok")
            return []

    entry = BibEntry(key="mybook", entry_type="book", fields={"title": "A Book"})
    asyncio.run(verify_entry(entry, [AcademicOnly(), BookCompatible()], Config()))
    assert "academic_only" not in call_log
    assert "book_ok" in call_log


def test_arxiv_skipped_without_arxiv_id():
    """arXiv provider should be skipped if entry has no arXiv ID."""
    call_log = []

    class MockArxiv:
        provider_name = "arxiv"
        supported_categories = frozenset({"academic"})
        min_delay_seconds = 3.0

        async def lookup_by_id(self, identifier, id_type):
            call_log.append("arxiv")
            return []

        async def search(self, title, authors=None, year=None):
            call_log.append("arxiv")
            return []

    entry = BibEntry(
        key="noid",
        entry_type="article",
        fields={"title": "No arXiv ID Here"},
    )
    asyncio.run(verify_entry(entry, [MockArxiv()], Config()))
    assert "arxiv" not in call_log


def test_result_includes_entry_type_and_category():
    entry = BibEntry(
        key="demo",
        entry_type="article",
        fields={"title": "Exact Match", "author": "Alice Smith", "year": "2024"},
    )
    result = asyncio.run(verify_entry(entry, [RankedProvider()], Config()))
    assert result.entry_type == "article"
    assert result.category == "academic"


def test_exact_doi_match_is_verified_with_sparse_metadata():
    class DOIProvider:
        provider_name = "doi"
        supported_categories = frozenset({"academic"})
        min_delay_seconds = 0.0

        async def lookup_by_id(self, identifier, id_type):
            assert (identifier, id_type) == ("10.1000/example", "doi")
            return [
                Candidate(
                    provider=self.provider_name,
                    provider_id="doi-result",
                    title="Exact Title",
                    ids={"doi": "10.1000/example"},
                )
            ]

        async def search(self, title, authors=None, year=None):
            raise AssertionError("An exact DOI result should not need title search")

    entry = BibEntry(
        key="sparse",
        entry_type="article",
        fields={
            "title": "Exact Title",
            "doi": "https://doi.org/10.1000/EXAMPLE",
        },
    )

    result = asyncio.run(verify_entry(entry, [DOIProvider()], Config()))

    assert result.verdict == Verdict.VERIFIED
    assert result.score == 1.0
    assert "DOI" in result.reasons[0]


def test_exact_doi_with_conflicting_title_is_flagged():
    class DOIProvider:
        provider_name = "doi"
        supported_categories = frozenset({"academic"})
        min_delay_seconds = 0.0

        async def lookup_by_id(self, identifier, id_type):
            return [
                Candidate(
                    provider=self.provider_name,
                    provider_id="doi-result",
                    title="A Completely Different Paper",
                    ids={"doi": identifier},
                )
            ]

        async def search(self, title, authors=None, year=None):
            raise AssertionError("An exact DOI result should not need title search")

    entry = BibEntry(
        key="conflict",
        entry_type="article",
        fields={"title": "Network Science", "doi": "10.1000/example"},
    )

    result = asyncio.run(verify_entry(entry, [DOIProvider()], Config()))

    assert result.verdict == Verdict.CONFLICT
    assert "conflicting title" in result.reasons[0]


def test_exact_doi_with_dropped_subtitle_is_not_a_conflict():
    class DOIProvider:
        provider_name = "doi"
        supported_categories = frozenset({"academic"})
        min_delay_seconds = 0.0

        async def lookup_by_id(self, identifier, id_type):
            return [
                Candidate(
                    provider=self.provider_name,
                    provider_id="doi-result",
                    title="Closing the AI accountability gap",
                    ids={"doi": identifier},
                )
            ]

        async def search(self, title, authors=None, year=None):
            raise AssertionError("An exact DOI result should not need title search")

    entry = BibEntry(
        key="subtitle",
        entry_type="inproceedings",
        fields={
            "title": "Closing the {{AI}} Accountability Gap: Defining an "
            "End-to-End Framework for Internal Algorithmic Auditing",
            "doi": "10.1145/3351095.3372873",
        },
    )

    result = asyncio.run(verify_entry(entry, [DOIProvider()], Config()))

    assert result.verdict != Verdict.CONFLICT


def test_verify_entries_bounds_provider_concurrency():
    active = 0
    max_active = 0

    class SlowProvider:
        provider_name = "slow"
        supported_categories = frozenset({"academic"})
        min_delay_seconds = 0.0

        async def lookup_by_id(self, identifier, id_type):
            return []

        async def search(self, title, authors=None, year=None):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return []

    entries = [
        BibEntry(key=str(index), entry_type="article", fields={"title": str(index)})
        for index in range(8)
    ]
    config = Config(max_concurrent_providers=2)

    results = asyncio.run(verify_entries(entries, [SlowProvider()], config))

    assert len(results) == len(entries)
    assert max_active == 2

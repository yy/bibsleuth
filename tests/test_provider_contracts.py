"""Mocked response contracts for every academic database provider."""

import asyncio

import httpx
import respx

from bibsleuth.providers.arxiv import ArxivProvider
from bibsleuth.providers.crossref import CrossRefProvider
from bibsleuth.providers.dblp import DBLPProvider
from bibsleuth.providers.openalex import OpenAlexProvider
from bibsleuth.providers.pubmed import PubMedProvider
from bibsleuth.providers.semantic_scholar import SemanticScholarProvider


async def _search(provider, title="Example"):
    provider.min_delay_seconds = 0
    try:
        return await provider.search(title)
    finally:
        await provider.close()


def test_openalex_search_contract():
    with respx.mock:
        respx.get("https://api.openalex.org/works").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "W1",
                            "title": "Example",
                            "publication_year": 2024,
                            "authorships": [
                                {"author": {"display_name": "Ada Lovelace"}}
                            ],
                            "doi": "https://doi.org/10.1000/example",
                        }
                    ]
                },
            )
        )
        candidates = asyncio.run(_search(OpenAlexProvider()))

    assert candidates[0].provider_id == "W1"
    assert candidates[0].ids["doi"] == "10.1000/example"


def test_semantic_scholar_search_contract():
    with respx.mock:
        respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "paperId": "S1",
                            "title": "Example",
                            "authors": [{"name": "Ada Lovelace"}],
                            "year": 2024,
                            "externalIds": {"DOI": "10.1000/example"},
                        }
                    ]
                },
            )
        )
        candidates = asyncio.run(_search(SemanticScholarProvider()))

    assert candidates[0].provider_id == "S1"
    assert candidates[0].authors == ["Ada Lovelace"]


def test_crossref_search_contract():
    with respx.mock:
        respx.get("https://api.crossref.org/works").mock(
            return_value=httpx.Response(
                200,
                json={
                    "message": {
                        "items": [
                            {
                                "DOI": "10.1000/example",
                                "title": ["Example"],
                                "author": [{"given": "Ada", "family": "Lovelace"}],
                                "published-online": {"date-parts": [[2024, 1, 1]]},
                            }
                        ]
                    }
                },
            )
        )
        candidates = asyncio.run(_search(CrossRefProvider()))

    assert candidates[0].year == 2024
    assert candidates[0].url == "https://doi.org/10.1000/example"


def test_dblp_search_contract():
    with respx.mock:
        respx.get("https://dblp.org/search/publ/api").mock(
            return_value=httpx.Response(
                200,
                json={
                    "result": {
                        "hits": {
                            "hit": [
                                {
                                    "info": {
                                        "key": "conf/example",
                                        "title": "Example",
                                        "authors": {
                                            "author": [{"text": "Ada Lovelace"}]
                                        },
                                        "year": "2024",
                                    }
                                }
                            ]
                        }
                    }
                },
            )
        )
        candidates = asyncio.run(_search(DBLPProvider()))

    assert candidates[0].provider_id == "conf/example"
    assert candidates[0].year == 2024


def test_arxiv_search_contract():
    atom = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>https://arxiv.org/abs/2401.12345</id>
    <title>Example</title>
    <published>2024-01-01T00:00:00Z</published>
    <author><name>Ada Lovelace</name></author>
    <summary>An abstract.</summary>
  </entry>
</feed>
"""
    with respx.mock:
        respx.get("https://export.arxiv.org/api/query").mock(
            return_value=httpx.Response(200, text=atom)
        )
        candidates = asyncio.run(_search(ArxivProvider()))

    assert candidates[0].ids["arxiv"] == "2401.12345"
    assert candidates[0].abstract == "An abstract."


def test_pubmed_search_contract():
    with respx.mock:
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").mock(
            return_value=httpx.Response(
                200,
                json={"esearchresult": {"idlist": ["123"]}},
            )
        )
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi").mock(
            return_value=httpx.Response(
                200,
                json={
                    "result": {
                        "123": {
                            "title": "Example",
                            "authors": [{"name": "Lovelace A"}],
                            "pubdate": "2024 Jan",
                            "articleids": [
                                {"idtype": "doi", "value": "10.1000/example"}
                            ],
                        }
                    }
                },
            )
        )
        candidates = asyncio.run(_search(PubMedProvider()))

    assert candidates[0].provider_id == "123"
    assert candidates[0].year == 2024
    assert candidates[0].ids["doi"] == "10.1000/example"

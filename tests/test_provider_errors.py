"""Provider transport and HTTP error semantics."""

import asyncio

import httpx
import pytest
import respx

from bibsleuth.config import Config
from bibsleuth.providers.openalex import OpenAlexProvider
from bibsleuth.types import BibEntry, Verdict
from bibsleuth.verify.existence import verify_entry


def _run_openalex_status(status_code):
    async def run_check():
        provider = OpenAlexProvider()
        provider.max_retries = 0
        try:
            result = await verify_entry(
                BibEntry(
                    key="example",
                    entry_type="article",
                    fields={"title": "Example"},
                ),
                [provider],
                Config(),
            )
            return result
        finally:
            await provider.close()

    with respx.mock:
        respx.get("https://api.openalex.org/works").mock(
            return_value=httpx.Response(status_code, json={"error": "unavailable"})
        )
        return asyncio.run(run_check())


@pytest.mark.parametrize("status_code", [401, 429, 503])
def test_http_failure_is_not_reported_as_missing_paper(status_code):
    result = _run_openalex_status(status_code)

    assert result.verdict == Verdict.ERROR
    assert f"HTTP {status_code}" in result.reasons[0]


def test_not_found_response_remains_a_valid_empty_result():
    result = _run_openalex_status(404)

    assert result.verdict == Verdict.UNVERIFIED
    assert result.reasons == ["Not found in any database"]


def test_openalex_reconstructs_abstract_from_inverted_index():
    provider = OpenAlexProvider()

    candidate = provider._parse_work(
        {
            "id": "W1",
            "title": "Example",
            "abstract_inverted_index": {
                "Second": [1],
                "First": [0],
                "word": [2],
            },
        }
    )

    assert candidate.abstract == "First Second word"


def test_provider_runtime_controls_are_configurable():
    provider = OpenAlexProvider(timeout_seconds=2.5, max_retries=7)

    assert provider.timeout_seconds == 2.5
    assert provider.max_retries == 7

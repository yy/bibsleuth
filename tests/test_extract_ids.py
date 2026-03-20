"""Tests for ID extraction."""

from bibsleuth.parse.extract_ids import (
    extract_arxiv,
    extract_doi,
    extract_ids,
    extract_isbn,
)


class TestExtractDOI:
    def test_basic(self):
        assert (
            extract_doi("doi: 10.1126/science.286.5439.509")
            == "10.1126/science.286.5439.509"
        )

    def test_with_url(self):
        result = extract_doi("https://doi.org/10.1038/30918")
        assert result == "10.1038/30918"

    def test_trailing_punct(self):
        assert extract_doi("10.1234/test.") == "10.1234/test"

    def test_no_match(self):
        assert extract_doi("no doi here") is None


class TestExtractArxiv:
    def test_new_format(self):
        assert extract_arxiv("arxiv:2301.12345") == "2301.12345"

    def test_without_prefix(self):
        assert extract_arxiv("paper 2301.12345 is great") == "2301.12345"

    def test_old_format(self):
        assert extract_arxiv("cs/0512077") == "cs/0512077"

    def test_no_match(self):
        assert extract_arxiv("no arxiv here") is None


class TestExtractISBN:
    def test_isbn13(self):
        assert extract_isbn("ISBN 978-0-306-40615-7") == "9780306406157"

    def test_no_match(self):
        assert extract_isbn("no isbn here") is None


class TestExtractIDs:
    def test_multiple(self):
        text = "DOI: 10.1234/test, arXiv: 2301.12345"
        ids = extract_ids(text)
        assert "doi" in ids
        assert "arxiv" in ids

    def test_empty(self):
        assert extract_ids("nothing here") == {}

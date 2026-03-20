"""Tests for text normalization."""

from bibsleuth.parse.normalize import (
    author_family_names,
    normalize_author_name,
    normalize_title,
    normalize_venue,
)


class TestNormalizeTitle:
    def test_basic(self):
        assert normalize_title("Hello World") == "hello world"

    def test_latex_commands(self):
        assert normalize_title(r"\textbf{Bold} Title") == "bold title"

    def test_braces(self):
        assert normalize_title("{Network} {Science}") == "network science"

    def test_latex_accents(self):
        result = normalize_title(r"Barab{\'a}si and Albert")
        assert "barabasi" in result or "baraba si" in result

    def test_greek_letters(self):
        assert "alpha" in normalize_title(r"The $\alpha$ model")

    def test_unicode_accents(self):
        result = normalize_title("Réka and László")
        assert "reka" in result
        assert "laszlo" in result

    def test_empty(self):
        assert normalize_title("") == ""

    def test_none_like(self):
        assert normalize_title("") == ""


class TestNormalizeVenue:
    def test_basic(self):
        assert normalize_venue("Nature") == "nature"

    def test_accents(self):
        result = normalize_venue("Réseau Français")
        assert "reseau" in result


class TestNormalizeAuthor:
    def test_basic(self):
        assert normalize_author_name("John Smith") == "john smith"

    def test_latex_accent(self):
        result = normalize_author_name(r"Barab{\'a}si, Albert-L{\'a}szl{\'o}")
        assert "barabasi" in result

    def test_empty(self):
        assert normalize_author_name("") == ""


class TestAuthorFamilyNames:
    def test_basic(self):
        assert author_family_names(["John Smith", "Jane Doe"]) == ["smith", "doe"]

    def test_dedup(self):
        assert author_family_names(["J. Smith", "K. Smith"]) == ["smith"]

    def test_empty(self):
        assert author_family_names([]) == []

    def test_single_name(self):
        assert author_family_names(["Madonna"]) == ["madonna"]

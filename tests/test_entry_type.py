"""Tests for entry type classification."""

from bibsleuth.types import EntryCategory, classify_entry_type


def test_academic_types():
    for t in ["article", "inproceedings", "conference", "phdthesis", "techreport"]:
        assert classify_entry_type(t) == EntryCategory.ACADEMIC


def test_book_types():
    for t in ["book", "inbook", "booklet"]:
        assert classify_entry_type(t) == EntryCategory.BOOK


def test_non_searchable_types():
    for t in [
        "misc",
        "software",
        "dataset",
        "online",
        "webpage",
        "manual",
        "electronic",
    ]:
        assert classify_entry_type(t) == EntryCategory.NON_SEARCHABLE


def test_unknown_defaults_to_academic():
    assert classify_entry_type("xyzunknown") == EntryCategory.ACADEMIC


def test_case_insensitive():
    assert classify_entry_type("Article") == EntryCategory.ACADEMIC
    assert classify_entry_type("BOOK") == EntryCategory.BOOK
    assert classify_entry_type("Misc") == EntryCategory.NON_SEARCHABLE

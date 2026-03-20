"""Extract DOI, arXiv ID, and ISBN from text.

Adapted from CiteSleuth (MIT license, https://github.com/uncrafted/CiteSleuth).
"""

from __future__ import annotations

import re

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
ARXIV_RE = re.compile(
    r"(?:arxiv:)?(?P<id>\d{4}\.\d{4,5}|[a-z\-]+/\d{7})",
    re.IGNORECASE,
)
ISBN_RE = re.compile(r"(?P<isbn>(?:97[89][\-\s]?)?\d[\d\-\s]{8,}[\dXx])")


def _strip_trailing_punct(value: str) -> str:
    return value.rstrip('.,;:()[]{}<>"')


def extract_doi(text: str) -> str | None:
    match = DOI_RE.search(text)
    if not match:
        return None
    return _strip_trailing_punct(match.group(0))


def extract_arxiv(text: str) -> str | None:
    match = ARXIV_RE.search(text)
    if not match:
        return None
    return match.group("id")


def _isbn_check_digit(isbn_digits: str) -> bool:
    if len(isbn_digits) == 10:
        total = sum(
            idx * int(char)
            for idx, char in enumerate(isbn_digits[:9], start=1)
            if char.isdigit()
        )
        if any(not c.isdigit() for c in isbn_digits[:9]):
            return False
        check = total % 11
        expected = "X" if check == 10 else str(check)
        return isbn_digits[-1].upper() == expected
    if len(isbn_digits) == 13 and isbn_digits.isdigit():
        total = sum(
            int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(isbn_digits[:12])
        )
        check = (10 - (total % 10)) % 10
        return isbn_digits[-1] == str(check)
    return False


def extract_isbn(text: str) -> str | None:
    for match in ISBN_RE.finditer(text):
        raw = match.group("isbn")
        digits = re.sub(r"[^0-9Xx]", "", raw)
        if len(digits) in {10, 13} and _isbn_check_digit(digits):
            return digits.upper()
    return None


def extract_ids(text: str) -> dict[str, str]:
    """Extract all recognized identifiers from text."""
    ids: dict[str, str] = {}
    doi = extract_doi(text)
    if doi:
        ids["doi"] = doi
    arxiv = extract_arxiv(text)
    if arxiv:
        ids["arxiv"] = arxiv
    isbn = extract_isbn(text)
    if isbn:
        ids["isbn"] = isbn
    return ids

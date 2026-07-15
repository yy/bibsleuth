"""Tests for BibTeX parsing."""

from bibsleuth.parse.bib import parse_bib
from bibsleuth.parse.extract_ids import extract_ids
from bibsleuth.types import BibEntry


def test_parse_bib_preserves_raw_entry_text(tmp_path):
    bib_path = tmp_path / "refs.bib"
    bib_path.write_text(
        """@article{demo,
  title = {Example},
  eprint = {arXiv:1234.5678},
  url = {https://arxiv.org/abs/1234.5678}
}
""",
        encoding="utf-8",
    )

    entry = parse_bib(bib_path)[0]

    assert "arXiv:1234.5678" in entry.raw
    assert extract_ids(entry.raw)["arxiv"] == "1234.5678"


def test_author_list_preserves_braced_corporate_names():
    entry = BibEntry(
        key="demo",
        entry_type="article",
        fields={"author": "{Research and Development Corporation} and Smith, Jane"},
    )

    assert entry.authors == [
        "{Research and Development Corporation}",
        "Smith, Jane",
    ]

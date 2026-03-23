"""Tests for BibTeX parsing."""

from bibsleuth.parse.bib import parse_bib
from bibsleuth.parse.extract_ids import extract_ids


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

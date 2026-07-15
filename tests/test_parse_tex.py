"""Tests for TeX parsing helpers."""

import pytest

from bibsleuth.parse.tex import (
    TexProjectError,
    extract_citations,
    extract_claims,
    find_bib_path,
    find_bib_paths,
)


def test_find_bib_path_skips_commented_directives(tmp_path):
    tex_path = tmp_path / "paper.tex"
    bib_path = tmp_path / "refs.bib"
    bib_path.write_text("", encoding="utf-8")
    tex_path.write_text(
        "% \\bibliography{old}\n\\bibliography{refs}\n",
        encoding="utf-8",
    )

    assert find_bib_path(tex_path) == bib_path


def test_find_bib_path_handles_multiple_bibliographies(tmp_path):
    tex_path = tmp_path / "paper.tex"
    first = tmp_path / "refs1.bib"
    second = tmp_path / "refs2.bib"
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")
    tex_path.write_text("\\bibliography{refs1,refs2}\n", encoding="utf-8")

    assert find_bib_path(tex_path) == first


def test_extract_citations_tracks_section(tmp_path):
    tex_path = tmp_path / "paper.tex"
    tex_path.write_text(
        "\\section{Methods}\nWe follow prior work \\cite{smith2024}.\n",
        encoding="utf-8",
    )

    contexts = extract_citations(tex_path)

    assert len(contexts) == 1
    assert contexts[0].section == "Methods"


def test_extract_claims_marks_cited_sentences_and_sections(tmp_path):
    tex_path = tmp_path / "paper.tex"
    tex_path.write_text(
        "\\section{Results}\n"
        "This claim cites prior work \\cite{smith2024}. "
        "This follow-up sentence does not.\n",
        encoding="utf-8",
    )

    claims = extract_claims(tex_path)

    assert [claim.section for claim in claims] == ["Results", "Results"]
    assert claims[0].cited_keys == ["smith2024"]
    assert claims[1].cited_keys == []


def test_extract_citations_recurses_through_inputs(tmp_path):
    sections = tmp_path / "sections"
    sections.mkdir()
    root = tmp_path / "paper.tex"
    child = sections / "intro.tex"
    root.write_text("\\input{sections/intro}\n", encoding="utf-8")
    child.write_text(
        "\\section{Introduction}\nA nested claim \\cite{nested}.\n",
        encoding="utf-8",
    )

    contexts = extract_citations(root)

    assert [context.key for context in contexts] == ["nested"]
    assert contexts[0].section == "Introduction"


def test_find_bib_paths_across_project_files(tmp_path):
    sections = tmp_path / "sections"
    sections.mkdir()
    root = tmp_path / "paper.tex"
    child = sections / "methods.tex"
    root_bib = tmp_path / "main.bib"
    child_bib = sections / "methods.bib"
    root_bib.write_text("", encoding="utf-8")
    child_bib.write_text("", encoding="utf-8")
    root.write_text(
        "\\addbibresource{main.bib}\n\\input{sections/methods}\n",
        encoding="utf-8",
    )
    child.write_text("\\bibliography{methods}\n", encoding="utf-8")

    assert find_bib_paths(root) == [root_bib.resolve(), child_bib.resolve()]


def test_tex_include_cycle_is_reported(tmp_path):
    first = tmp_path / "first.tex"
    second = tmp_path / "second.tex"
    first.write_text("\\input{second}\n", encoding="utf-8")
    second.write_text("\\input{first}\n", encoding="utf-8")

    with pytest.raises(TexProjectError, match="cycle"):
        extract_citations(first)


def test_missing_bibliography_is_reported(tmp_path):
    tex_path = tmp_path / "paper.tex"
    tex_path.write_text("\\bibliography{missing}\n", encoding="utf-8")

    with pytest.raises(TexProjectError, match="Bibliography file not found"):
        find_bib_paths(tex_path)

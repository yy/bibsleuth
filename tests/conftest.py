"""Shared test fixtures."""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_bib():
    return FIXTURES_DIR / "sample.bib"


@pytest.fixture
def sample_tex():
    return FIXTURES_DIR / "sample.tex"

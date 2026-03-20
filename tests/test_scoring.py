"""Tests for candidate scoring."""

from bibsleuth.verify.scoring import (
    author_overlap,
    score_candidate,
    title_similarity,
    venue_similarity,
    year_score,
)


class TestTitleSimilarity:
    def test_identical(self):
        score = title_similarity("Emergence of Scaling", "Emergence of Scaling")
        assert score == 1.0

    def test_similar(self):
        score = title_similarity(
            "Emergence of Scaling in Random Networks",
            "Emergence of scaling in random networks",
        )
        assert score > 0.9

    def test_different(self):
        score = title_similarity("Network Science", "Quantum Computing")
        assert score < 0.3

    def test_empty(self):
        assert title_similarity("", "something") == 0.0
        assert title_similarity("something", "") == 0.0


class TestAuthorOverlap:
    def test_identical(self):
        score = author_overlap(["Albert Einstein"], ["Albert Einstein"])
        assert score == 1.0

    def test_partial(self):
        score = author_overlap(
            ["John Smith", "Jane Doe"],
            ["John Smith", "Bob Jones"],
        )
        assert score == 0.5

    def test_empty(self):
        assert author_overlap([], ["someone"]) == 0.0


class TestYearScore:
    def test_exact(self):
        assert year_score(2020, 2020) == 1.0

    def test_off_by_one(self):
        assert year_score(2020, 2021) == 0.5

    def test_off_by_two(self):
        assert year_score(2020, 2022) == 0.2

    def test_far_apart(self):
        assert year_score(2020, 2025) == 0.0

    def test_invalid(self):
        assert year_score(None, 2020) == 0.0


class TestVenueSimilarity:
    def test_identical(self):
        score = venue_similarity("Nature", "Nature")
        assert score == 1.0

    def test_different(self):
        score = venue_similarity("Nature", "Science")
        assert score == 0.0


class TestScoreCandidate:
    def test_perfect_match(self):
        ref = {
            "title": "Network Science",
            "authors": ["Albert Barabasi"],
            "year": 2016,
            "venue": "Cambridge Press",
        }
        score, breakdown = score_candidate(ref, ref)
        assert score > 0.99

    def test_partial_match(self):
        ref = {
            "title": "Network Science",
            "authors": ["Barabasi"],
            "year": 2016,
            "venue": "Nature",
        }
        cand = {
            "title": "Network Science Review",
            "authors": ["Newman"],
            "year": 2016,
            "venue": "Science",
        }
        score, breakdown = score_candidate(ref, cand)
        assert 0.0 < score < 1.0
        assert "title" in breakdown

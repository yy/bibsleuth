"""Weighted similarity scoring for candidate matching.

Adapted from CiteSleuth (MIT license, https://github.com/uncrafted/CiteSleuth).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..parse.normalize import author_family_names, normalize_title, normalize_venue

TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass
class ScoreConfig:
    title_weight: float = 0.5
    author_weight: float = 0.2
    year_weight: float = 0.2
    venue_weight: float = 0.1


def _tokenize(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text or ""))


def title_similarity(title_a: str, title_b: str) -> float:
    norm_a = normalize_title(title_a)
    norm_b = normalize_title(title_b)
    if not norm_a or not norm_b:
        return 0.0
    tokens_a = _tokenize(norm_a)
    tokens_b = _tokenize(norm_b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    jaccard = len(intersection) / len(union)
    # Short title subset bonus
    if len(tokens_a) <= 4 or len(tokens_b) <= 4:
        if tokens_a.issubset(tokens_b) or tokens_b.issubset(tokens_a):
            return max(jaccard, 0.8)
    return jaccard


def author_overlap(authors_a: list[str], authors_b: list[str]) -> float:
    fam_a = set(author_family_names(authors_a))
    fam_b = set(author_family_names(authors_b))
    if not fam_a or not fam_b:
        return 0.0
    return len(fam_a & fam_b) / max(len(fam_a), len(fam_b))


def year_score(year_a, year_b) -> float:
    try:
        ya, yb = int(year_a), int(year_b)
    except (TypeError, ValueError):
        return 0.0
    diff = abs(ya - yb)
    if diff == 0:
        return 1.0
    if diff == 1:
        return 0.5
    if diff == 2:
        return 0.2
    return 0.0


def venue_similarity(venue_a: str, venue_b: str) -> float:
    norm_a = normalize_venue(venue_a or "")
    norm_b = normalize_venue(venue_b or "")
    if not norm_a or not norm_b:
        return 0.0
    tokens_a = _tokenize(norm_a)
    tokens_b = _tokenize(norm_b)
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def score_candidate(
    ref_fields: dict[str, object],
    candidate_fields: dict[str, object],
    config: ScoreConfig | None = None,
) -> tuple[float, dict[str, float]]:
    """Score a candidate against a reference entry. Returns (score, breakdown)."""
    config = config or ScoreConfig()
    ts = title_similarity(
        str(ref_fields.get("title", "")),
        str(candidate_fields.get("title", "")),
    )
    aus = author_overlap(
        ref_fields.get("authors", []) or [],
        candidate_fields.get("authors", []) or [],
    )
    ys = year_score(ref_fields.get("year"), candidate_fields.get("year"))
    vs = venue_similarity(
        str(ref_fields.get("venue", "")),
        str(candidate_fields.get("venue", "")),
    )

    score = (
        ts * config.title_weight
        + aus * config.author_weight
        + ys * config.year_weight
        + vs * config.venue_weight
    )
    breakdown = {"title": ts, "authors": aus, "year": ys, "venue": vs}
    return score, breakdown

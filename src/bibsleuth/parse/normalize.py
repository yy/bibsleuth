"""Text normalization for titles, authors, and venues.

Core logic adapted from CiteSleuth (MIT license, https://github.com/uncrafted/CiteSleuth).
Enhanced with accent stripping and LaTeX accent expansion patterns inspired by
hallucinator.
"""

from __future__ import annotations

import re
import unicodedata

LATEX_COMMAND_WITH_ARG = re.compile(r"\\[a-zA-Z]+\*?\{([^}]*)\}")
LATEX_COMMAND = re.compile(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?")
NON_WORD = re.compile(r"[^a-z0-9\s]")

# LaTeX accent commands -> base character
LATEX_ACCENTS = re.compile(
    r"""\\[`'^"~=.uvHtcdb]\{([a-zA-Z])\}"""  # e.g. \"{o} -> o
    r"""|\\[`'^"~=.uvHtcdb]([a-zA-Z])(?![a-zA-Z])"""  # e.g. \"o -> o
)

# Common Greek letters in LaTeX
GREEK_LETTERS = {
    "alpha": "alpha",
    "beta": "beta",
    "gamma": "gamma",
    "delta": "delta",
    "epsilon": "epsilon",
    "zeta": "zeta",
    "eta": "eta",
    "theta": "theta",
    "iota": "iota",
    "kappa": "kappa",
    "lambda": "lambda",
    "mu": "mu",
    "nu": "nu",
    "pi": "pi",
    "rho": "rho",
    "sigma": "sigma",
    "tau": "tau",
    "phi": "phi",
    "chi": "chi",
    "psi": "psi",
    "omega": "omega",
}

GREEK_RE = re.compile(r"\\(" + "|".join(GREEK_LETTERS.keys()) + r")\b", re.IGNORECASE)


def _expand_latex_accents(text: str) -> str:
    """Expand LaTeX accent commands to their base characters."""
    text = LATEX_ACCENTS.sub(lambda m: m.group(1) or m.group(2), text)
    return text


def _expand_greek(text: str) -> str:
    """Replace \\alpha etc. with the word 'alpha'."""
    return GREEK_RE.sub(
        lambda m: GREEK_LETTERS.get(m.group(1).lower(), m.group(1)), text
    )


def _strip_accents(text: str) -> str:
    """Strip combining diacritical marks via NFKD decomposition."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_title(title: str) -> str:
    """Normalize a title for fuzzy comparison."""
    if not title:
        return ""
    title = _expand_latex_accents(title)
    title = _expand_greek(title)
    title = LATEX_COMMAND_WITH_ARG.sub(r"\1", title)
    title = title.replace("{", "").replace("}", "")
    title = LATEX_COMMAND.sub(" ", title)
    title = _strip_accents(title)
    title = title.lower()
    title = NON_WORD.sub(" ", title)
    return _collapse_whitespace(title)


def normalize_venue(venue: str) -> str:
    """Normalize a venue name for fuzzy comparison."""
    if not venue:
        return ""
    venue = _strip_accents(venue)
    venue = venue.lower()
    venue = NON_WORD.sub(" ", venue)
    return _collapse_whitespace(venue)


def normalize_author_name(name: str) -> str:
    """Normalize a single author name."""
    if not name:
        return ""
    name = _expand_latex_accents(name)
    name = name.replace("{", "").replace("}", "")
    name = _strip_accents(name)
    name = name.lower()
    name = NON_WORD.sub(" ", name)
    return _collapse_whitespace(name)


def author_family_names(authors: list[str]) -> list[str]:
    """Extract unique family names in order from a list of author strings."""
    seen: set[str] = set()
    families: list[str] = []
    for author in authors:
        normalized = normalize_author_name(author)
        if not normalized:
            continue
        parts = normalized.split()
        family = parts[-1]
        if family not in seen:
            seen.add(family)
            families.append(family)
    return families

"""Missing citation suggestions: find papers that should be cited."""

from __future__ import annotations

from ..config import Config
from ..types import LLMAnalysis
from .client import complete

PROMPT_TEMPLATE = """\
You are an academic literature expert. Given a claim from a paper, suggest papers \
that should be cited to support this claim. Focus on well-known, highly-cited papers.

## Claim
{claim}

## Context
{context}

## Instructions
Respond with a JSON object:
- "suggestions": list of objects, each with "title", "authors" (list), "year", and "reason"
- Suggest 3-5 papers maximum
- Only suggest papers you are confident actually exist
"""


async def suggest_citations(
    claim: str,
    context: str,
    config: Config,
) -> LLMAnalysis:
    """Suggest papers that should be cited for a given claim."""
    prompt = PROMPT_TEMPLATE.format(claim=claim, context=context)
    response = await complete(prompt, config)

    import json
    import re

    suggested = []
    json_match = re.search(r"\{[^}]+\}", response, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            suggested = data.get("suggestions", [])
        except json.JSONDecodeError:
            pass

    return LLMAnalysis(
        key="",
        explanation=response,
        suggested_papers=suggested,
    )

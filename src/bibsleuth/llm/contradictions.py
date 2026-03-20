"""Contradicting evidence detection: surface counterarguments in the literature."""

from __future__ import annotations

from ..config import Config
from ..types import LLMAnalysis
from .client import complete

PROMPT_TEMPLATE = """\
You are an academic literature expert. Given a claim from a paper, identify well-known \
papers that present contradicting evidence or opposing viewpoints.

## Claim
{claim}

## Context
{context}

## Instructions
Respond with a JSON object:
- "contradictions": list of objects, each with "title", "authors" (list), "year", and "how_it_contradicts"
- Only suggest papers you are confident actually exist
- Focus on well-cited papers with genuine disagreements, not minor nuances
"""


async def find_contradictions(
    claim: str,
    context: str,
    config: Config,
) -> LLMAnalysis:
    """Find papers that contradict a given claim."""
    prompt = PROMPT_TEMPLATE.format(claim=claim, context=context)
    response = await complete(prompt, config)

    import json
    import re

    contradictions = []
    json_match = re.search(r"\{[^}]+\}", response, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            contradictions = data.get("contradictions", [])
        except json.JSONDecodeError:
            pass

    return LLMAnalysis(
        key="",
        explanation=response,
        contradictions=contradictions,
    )

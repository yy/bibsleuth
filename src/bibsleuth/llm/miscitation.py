"""Mis-citation detection: does the cited paper support the claim?"""

from __future__ import annotations

from ..config import Config
from ..types import CitingContext, LLMAnalysis
from .client import complete

PROMPT_TEMPLATE = """\
You are an academic citation verifier. Given a claim from a paper and the abstract \
of a cited paper, assess whether the cited paper supports the claim being made.

## Claim (from the citing paper)
{claim}

## Cited paper abstract
{abstract}

## Instructions
Respond with a JSON object:
- "supported": true if the abstract supports the claim, false if it contradicts or is unrelated, null if inconclusive
- "explanation": brief explanation (1-2 sentences)
"""


async def check_miscitation(
    context: CitingContext,
    abstract: str,
    config: Config,
) -> LLMAnalysis:
    """Check whether a citation supports the claim being made."""
    prompt = PROMPT_TEMPLATE.format(claim=context.sentence, abstract=abstract)
    response = await complete(prompt, config)

    # Parse response (best-effort JSON extraction)
    import json
    import re

    supported = None
    explanation = response

    json_match = re.search(r"\{[^}]+\}", response, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            supported = data.get("supported")
            explanation = data.get("explanation", response)
        except json.JSONDecodeError:
            pass

    return LLMAnalysis(
        key=context.key,
        supported=supported,
        explanation=explanation,
    )

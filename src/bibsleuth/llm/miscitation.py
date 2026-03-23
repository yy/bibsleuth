"""Mis-citation detection: does the cited paper support the claim?"""

from __future__ import annotations

from ..config import Config
from ..types import CitingContext, LLMAnalysis
from .client import complete
from .parsing import parse_json_object

PROMPT_TEMPLATE = """\
You are an academic citation verifier. Given a claim from a paper and the abstract \
of a cited paper, assess whether the cited paper supports the claim being made.

## Claim (from the citing paper)
{claim}

## Cited paper abstract
{abstract}

## Instructions
Respond with a JSON object:
- "supported": true if the abstract supports the claim, false if it
  contradicts or is unrelated, null if inconclusive
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

    supported = None
    explanation = response

    data = parse_json_object(response)
    if data:
        supported = data.get("supported")
        explanation = data.get("explanation", response)

    return LLMAnalysis(
        key=context.key,
        claim=context.sentence,
        section=context.section,
        supported=supported,
        explanation=explanation,
    )

"""Shared helpers for parsing structured LLM output."""

from __future__ import annotations

import json
from typing import Any


def parse_json_object(response: str) -> dict[str, Any] | None:
    """Extract the first JSON object embedded in a response string."""
    decoder = json.JSONDecoder()

    for index, char in enumerate(response):
        if char != "{":
            continue
        try:
            data, _ = decoder.raw_decode(response[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data

    return None

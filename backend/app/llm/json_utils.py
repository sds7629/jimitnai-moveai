"""Small shared helper for parsing structured JSON out of LLM text output.

Both the response-design and simulation stages instruct the LLM to respond
with JSON only, but real (and fake/test) LLM output commonly wraps the JSON
in a markdown code fence (```json ... ```) or has leading/trailing
whitespace/prose. This module centralizes that one bit of defensive
stripping so both stages parse LLM JSON the same way instead of
duplicating slightly-different regexes.
"""

from __future__ import annotations

import json
import re

_CODE_FENCE_PREFIX = re.compile(r"^```(?:json)?\s*", re.IGNORECASE)
_CODE_FENCE_SUFFIX = re.compile(r"\s*```\s*$")


def extract_json(raw_text: str) -> object:
    """Strips an optional markdown code fence and parses the remainder as
    JSON. Raises json.JSONDecodeError (via json.loads) if the cleaned text
    still isn't valid JSON -- callers are expected to catch that alongside
    any schema-level validation error and treat both as "the LLM violated
    the response contract"."""

    text = raw_text.strip()
    text = _CODE_FENCE_PREFIX.sub("", text)
    text = _CODE_FENCE_SUFFIX.sub("", text)
    text = text.strip()
    return json.loads(text)

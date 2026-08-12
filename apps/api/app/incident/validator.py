"""Validates raw `LLMProvider` output against `LLMNarrativeOutput` using
Pydantic — never allows arbitrary model output to bypass schema
validation. `parse_llm_output()` never raises: malformed output is a
completely normal, expected condition (any provider, including a well-
behaved one, can occasionally return prose instead of JSON), and the
caller's response is always the same — fall back to the deterministic
narrative (`app.incident.fallback`) — so there is nothing useful an
exception would communicate that a `None` return doesn't already.
"""

import json

from pydantic import ValidationError

from app.incident.schemas import LLMNarrativeOutput


def parse_llm_output(raw: str) -> LLMNarrativeOutput | None:
    """Attempts a direct JSON parse first; if that fails, attempts one
    safe, mechanical repair (stripping a markdown code fence — a common
    LLM formatting quirk, not a semantic guess about the content) and
    retries once. Returns `None` (never raises) if the result still isn't
    valid JSON, or is valid JSON that doesn't satisfy `LLMNarrativeOutput`
    (e.g. missing required fields, wrong types).
    """
    for candidate in (raw, _strip_code_fence(raw)):
        parsed = _try_parse(candidate)
        if parsed is not None:
            return parsed
    return None


def _try_parse(candidate: str) -> LLMNarrativeOutput | None:
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    try:
        return LLMNarrativeOutput.model_validate(data)
    except ValidationError:
        return None


def _strip_code_fence(text: str) -> str:
    """Removes a leading/trailing ```` ``` ```` or ```` ```json ```` fence,
    if present. A no-op (returns `text` unchanged) if there is no fence —
    safe to always try as the second parse attempt."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)

"""Rejects LLM narratives that make claims this codebase's structured
data cannot support — the hard backstop behind the prompt's own
instructions (`app.incident.prompt`), since a prompt is a request, not a
guarantee. A misbehaving or adversarially-prompted model can still ignore
its system prompt; this filter runs on every narrative regardless of how
well-behaved the model claimed to be.

Deliberately conservative: `filter_unsupported_claims()` returns `None`
(reject the *entire* narrative) rather than trying to surgically edit out
just the offending sentence — editing model-generated prose reliably is
its own hard problem, and a rejected narrative safely falls back to the
deterministic summarizer (`app.incident.fallback`), which can only ever
state what's really in the context anyway.

**This is a simple keyword/pattern filter, not a semantic understanding
of the text** — it catches direct mentions of banned topics, not every
possible paraphrase. It is a real, tested safety layer, not a claim of
perfect hallucination prevention — see "Hallucination controls" in
apps/api/README.md for the full, honest picture (prompt instructions +
structural exclusion of untrusted fields + this filter + deterministic
fallback, several layers, none individually perfect).
"""

import re

from app.incident.schemas import IncidentContext, LLMNarrativeOutput

# Topics the LLM must never claim anything about, regardless of what the
# prompt asked for — see the milestone's own "Grounding" requirement.
# "closure"/"closed" is banned (an official act this system has no data
# on) while "blocked" is not (our own AccessibilityStatus vocabulary,
# grounded in real, if unverified, data).
_BANNED_PATTERNS = [
    re.compile(r"\bcasualt", re.IGNORECASE),
    re.compile(r"\b(killed|deaths?|fatalit(y|ies)|injur(y|ies|ed))\b", re.IGNORECASE),
    re.compile(r"\btsunami\b", re.IGNORECASE),
    re.compile(r"\bflood(ing)?\b", re.IGNORECASE),
    re.compile(r"\bevacuat", re.IGNORECASE),
    re.compile(r"\b(weather|rainfall|storm|wind speed)\b", re.IGNORECASE),
    re.compile(r"\b(road )?closur|\bclosed\b", re.IGNORECASE),
]

# A decimal-degree-looking number (4+ decimal places is typical GPS
# precision) — a proxy for "this looks like an invented coordinate,"
# since IncidentContext never includes raw latitude/longitude for the
# model to legitimately repeat (only aggregate bounding boxes, which
# round-trip through the context as plain JSON, not prose the model would
# naturally quote back).
_COORDINATE_LIKE_PATTERN = re.compile(r"-?\d{1,3}\.\d{4,}")


def filter_unsupported_claims(
    narrative: LLMNarrativeOutput, context: IncidentContext
) -> LLMNarrativeOutput | None:
    """`None` if any free-text field contains a banned claim or an
    invented-looking coordinate; otherwise `narrative` unchanged. `context`
    is accepted (not currently used to whitelist anything) so a future,
    more precise grounding check — e.g. allowing a coordinate that
    actually matches `context.damage.spatial_bounds` — can be added here
    without changing the call site.
    """
    for text in _text_fields(narrative):
        if _contains_banned_claim(text) or _contains_invented_coordinate(text):
            return None
    return narrative


def _text_fields(narrative: LLMNarrativeOutput) -> list[str]:
    return [
        narrative.priority_area,
        narrative.route_summary,
        *narrative.key_findings,
        *narrative.limitations,
    ]


def _contains_banned_claim(text: str) -> bool:
    return any(pattern.search(text) for pattern in _BANNED_PATTERNS)


def _contains_invented_coordinate(text: str) -> bool:
    return _COORDINATE_LIKE_PATTERN.search(text) is not None

"""Groundedness, completeness, and unsupported-claim-rate evaluation for
`app.incident` narratives — reuses the real production grounding filter
(`app.incident.grounding.filter_unsupported_claims`) rather than
re-implementing it, so this evaluation measures the actual system's
behavior, not a parallel approximation of it.
"""

from collections.abc import Sequence

from app.incident.grounding import filter_unsupported_claims
from app.incident.schemas import IncidentContext, LLMNarrativeOutput

_UNAVAILABLE = "Information unavailable."
_COMPLETENESS_FIELDS = ("priority_area", "route_summary")


def is_grounded(narrative: LLMNarrativeOutput, context: IncidentContext) -> bool:
    """Reuses `app.incident.grounding.filter_unsupported_claims` — the
    real production grounding filter. `True` means the filter did not
    reject the narrative."""
    return filter_unsupported_claims(narrative, context) is not None


def completeness_score(narrative: LLMNarrativeOutput) -> float:
    """Fraction of the narrative's required free-text fields
    (`priority_area`, `route_summary`) that carry real content rather
    than the `"Information unavailable."` placeholder. `key_findings`/
    `limitations` are lists with no single "complete" state and are
    intentionally not scored here — this is a coarse, documented proxy,
    not a semantic completeness judgment."""
    present = sum(
        1 for field_name in _COMPLETENESS_FIELDS if getattr(narrative, field_name) != _UNAVAILABLE
    )
    return present / len(_COMPLETENESS_FIELDS)


def unsupported_claim_rate(
    narrative_context_pairs: Sequence[tuple[LLMNarrativeOutput, IncidentContext]],
) -> float:
    """Fraction of `(narrative, context)` pairs rejected by the real
    grounding filter. Requires at least one pair."""
    if not narrative_context_pairs:
        raise ValueError("unsupported_claim_rate requires at least one (narrative, context) pair.")
    rejected = sum(
        1 for narrative, context in narrative_context_pairs if not is_grounded(narrative, context)
    )
    return rejected / len(narrative_context_pairs)


def contains_supplied_facts(
    narrative: LLMNarrativeOutput, expected_substrings: Sequence[str]
) -> bool:
    """Whether every string in `expected_substrings` appears somewhere in
    the narrative's free text — verifies the narrative *correctly
    reflects supplied facts* (e.g. the exact `severely_damaged` count),
    which `is_grounded()` alone does not check (a grounded narrative could
    still omit the real numbers entirely)."""
    haystack = " ".join(
        [
            narrative.priority_area,
            narrative.route_summary,
            *narrative.key_findings,
            *narrative.limitations,
        ]
    )
    return all(substring in haystack for substring in expected_substrings)

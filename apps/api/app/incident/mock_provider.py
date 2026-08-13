"""A deterministic, offline `LLMProvider` for tests — never makes a
network call, never reads an API key. Unlike a fixed canned string, its
"valid" behavior derives the narrative *from* the given context, so tests
can assert the pipeline actually threads real context through to the
final briefing, not just that some hardcoded text came back.

Also exposes every failure mode `IncidentIntelligenceService` must handle
(`malformed`, `timeout`, `error`, `unsupported_claim`) so those paths are
testable without any real provider or network access — see
`tests/test_incident.py`.
"""

from typing import Literal

from app.incident.provider import LLMProviderError, LLMTimeoutError
from app.incident.schemas import IncidentContext, LLMNarrativeOutput

MockBehavior = Literal["valid", "malformed", "timeout", "error", "unsupported_claim"]

_UNAVAILABLE = "Information unavailable."


class MockLLMProvider:
    def __init__(self, behavior: MockBehavior = "valid") -> None:
        self._behavior = behavior

    def generate_incident_summary(self, context: IncidentContext) -> str:
        if self._behavior == "timeout":
            raise LLMTimeoutError("mock provider: simulated timeout")
        if self._behavior == "error":
            raise LLMProviderError("mock provider: simulated provider failure")
        if self._behavior == "malformed":
            return "{this is not valid json"
        if self._behavior == "unsupported_claim":
            return _unsupported_claim_narrative().model_dump_json()
        return _narrative_from_context(context).model_dump_json()


def _unsupported_claim_narrative() -> LLMNarrativeOutput:
    """Simulates a misbehaving model that ignored its system prompt —
    exercises `app.incident.grounding`'s content filter."""
    return LLMNarrativeOutput(
        priority_area="Casualties are expected near the affected structures.",
        route_summary="The route was closed due to an official evacuation order.",
        key_findings=["Heavy rain is forecast, worsening conditions."],
        limitations=["Data may be incomplete."],
    )


def _narrative_from_context(context: IncidentContext) -> LLMNarrativeOutput:
    damage = context.damage
    if damage.available and damage.summary is not None:
        priority_area = (
            f"{damage.summary.destroyed} destroyed and {damage.summary.severely_damaged} "
            "severely damaged structure(s) were detected."
        )
    else:
        priority_area = _UNAVAILABLE

    route = context.route
    if (
        route.available
        and route.selected_distance_meters is not None
        and route.selected_risk_score is not None
    ):
        route_summary = (
            f"Selected route: {route.selected_distance_meters:.0f}m "
            f"(risk {route.selected_risk_score:.2f})."
        )
    else:
        route_summary = _UNAVAILABLE

    findings = []
    if context.road_risk.available:
        findings.append(
            f"{context.road_risk.risky_edge_count} road segment(s) at high/critical risk."
        )
    limitations = [
        "Damage predictions may be inaccurate.",
        "Road risk is a modeled estimate, not a verified fact.",
    ]

    return LLMNarrativeOutput(
        priority_area=priority_area,
        route_summary=route_summary,
        key_findings=findings,
        limitations=limitations,
    )

"""The deterministic, template-based summarizer — no LLM, no network, no
external dependency of any kind. `build_fallback_narrative()` is a pure
function of `IncidentContext`; it can only ever state what's already in
the context, so it needs no grounding check of its own (unlike LLM
output — see `app.incident.grounding`).

`DeterministicSummaryProvider` wraps that same function as an
`LLMProvider`, so it can be configured as the *actual* active provider
(`Settings.LLM_PROVIDER = "deterministic"`, the default) — not merely a
last-resort fallback. This is what makes "no API key / LLM unavailable /
provider error / timeout / malformed output -> still produce a valid
incident briefing" true even when nothing else in the stack is
misbehaving: there is nothing to misbehave.
"""

from app.incident.schemas import IncidentContext, LLMNarrativeOutput

_STANDARD_LIMITATIONS = [
    "Damage predictions may be inaccurate.",
    "Road risk is a modeled estimate based on proximity to detected damage, not a verified fact.",
    "Road accessibility (blocked/restricted) has not been independently confirmed.",
]

_UNAVAILABLE = "Information unavailable."


def build_fallback_narrative(context: IncidentContext) -> LLMNarrativeOutput:
    return LLMNarrativeOutput(
        priority_area=_describe_priority_area(context),
        route_summary=_describe_route(context),
        key_findings=_key_findings(context),
        limitations=_limitations(context),
    )


def _describe_priority_area(context: IncidentContext) -> str:
    damage = context.damage
    if not damage.available or damage.summary is None:
        return _UNAVAILABLE
    if not damage.high_priority_structure_ids:
        return "No high-priority structures were identified in the detected damage."
    count = len(damage.high_priority_structure_ids)
    if damage.spatial_bounds is not None:
        # Deliberately low precision (2 decimal places, ~1km) — a rough
        # bounding area, not an implied exact/survey-grade coordinate.
        min_lon, min_lat, max_lon, max_lat = damage.spatial_bounds.coordinates
        return (
            f"{count} high-priority structure(s) were identified, within the approximate "
            f"bounding area [{min_lon:.2f}, {min_lat:.2f}] to [{max_lon:.2f}, {max_lat:.2f}]."
        )
    return (
        f"{count} high-priority structure(s) were identified "
        "(no georeferenced location available)."
    )


def _describe_route(context: IncidentContext) -> str:
    route = context.route
    if not route.available:
        return _UNAVAILABLE
    parts = []
    if route.selected_distance_meters is not None:
        parts.append(f"the selected route covers {route.selected_distance_meters:.0f}m")
    if route.selected_risk_score is not None:
        parts.append(f"an accumulated risk score of {route.selected_risk_score:.2f}")
    if route.baseline_distance_meters is not None:
        parts.append(f"versus a {route.baseline_distance_meters:.0f}m shortest-distance baseline")
    if route.detour_ratio is not None:
        parts.append(f"a detour ratio of {route.detour_ratio:.2f}")
    if route.avoided_high_risk_segment_count:
        parts.append(f"avoiding {route.avoided_high_risk_segment_count} high-risk segment(s)")
    if not parts:
        return _UNAVAILABLE
    return "Compared to the shortest-distance baseline, " + ", ".join(parts) + "."


def _key_findings(context: IncidentContext) -> list[str]:
    findings: list[str] = []
    damage = context.damage
    if damage.available and damage.summary is not None:
        summary = damage.summary
        findings.append(
            f"{summary.total_buildings} structure(s) assessed: {summary.damaged_buildings} damaged, "
            f"{summary.destroyed} destroyed."
        )
        if damage.average_confidence is not None:
            findings.append(f"Average detection confidence: {damage.average_confidence:.2f}.")
    else:
        findings.append(_UNAVAILABLE)

    road_risk = context.road_risk
    if road_risk.available:
        findings.append(
            f"{road_risk.risky_edge_count} of {road_risk.total_edges_assessed} assessed road "
            f"segment(s) are at high or critical modeled risk; {road_risk.blocked_edge_count} "
            f"segment(s) are recorded as blocked, {road_risk.restricted_edge_count} as restricted."
        )
    else:
        findings.append(f"Road risk: {_UNAVAILABLE}")

    return findings


def _limitations(context: IncidentContext) -> list[str]:
    limitations = list(_STANDARD_LIMITATIONS)
    if not context.damage.available:
        limitations.append("Damage analysis is not yet available for this incident.")
    if not context.road_risk.available:
        limitations.append("Road risk analysis is not available for this incident.")
    if not context.route.available:
        limitations.append("No route was requested or available for this incident.")
    return limitations


class DeterministicSummaryProvider:
    """The only `LLMProvider` implementation this milestone guarantees
    never fails. Never makes a network call, never reads an API key.
    Default production provider (`Settings.LLM_PROVIDER = "deterministic"`).
    """

    def generate_incident_summary(self, context: IncidentContext) -> str:
        return build_fallback_narrative(context).model_dump_json()

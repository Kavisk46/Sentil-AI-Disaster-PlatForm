"""The **deterministic, rule-based recommendation engine** (Phase 5).

Three independent, composable rules — each a pure function of real input
data plus already-computed `SearchZone`/`CapabilityMatchResult` objects,
never an LLM (project constraint: "Do NOT use an LLM for this
milestone. The architecture should allow an LLM or multimodal model to
be added later" — see `docs/architecture/intelligence.md` for how a
future model would plug in without changing this module's output
contract, `Recommendation`).

1. **Search-zone response** — a `HIGH`/`CRITICAL` `SearchZone` either
   gets a reconnaissance recommendation (when its evidence is
   incomplete/uncertain — investigate before committing a ground team),
   a ground-team deployment recommendation (when a capable, available,
   reachable team exists — see `app.intelligence.capability_matching`),
   or an escalation recommendation (when no eligible resource exists).
   Which of the three fires is itself evidence-driven, not arbitrary.
2. **Infrastructure inspection** — a non-operational bridge/road/tunnel
   is flagged for inspection *before* dispatch, exactly the "inspect
   blocked bridge before dispatching ground team" example the F2 brief
   gives (illustrative there; here it's a real, general rule keyed off
   `Infrastructure.status`, not a hardcoded scenario).
3. **Hazard avoidance** — a `HIGH`/`CRITICAL` hazard produces a
   recommendation to route around it.

If none of the above produce anything actionable, `generate_recommendations`
returns a single, honest `HOLD_PENDING_MORE_INFORMATION` recommendation
rather than a bare empty list that could be mistaken for an engine
failure (project constraint: "missing data is represented explicitly").
"""

from datetime import UTC, datetime
from uuid import uuid4

from app.intelligence.capability_matching import rank_candidates
from app.intelligence.config import CapabilityMatchingConfig
from app.intelligence.schemas import (
    Evidence,
    EvidenceSourceType,
    Hazard,
    HazardSeverity,
    Infrastructure,
    InfrastructureStatus,
    InfrastructureType,
    Recommendation,
    RecommendationAction,
    RecommendationPriority,
    Resource,
    ResourceCapability,
    SearchPriorityLevel,
    SearchZone,
    Uncertainty,
    UncertaintyLevel,
)

_HIGH_PRIORITY_LEVELS = frozenset({SearchPriorityLevel.HIGH, SearchPriorityLevel.CRITICAL})
_UNCERTAIN_EVIDENCE_LEVELS = frozenset({UncertaintyLevel.HIGH, UncertaintyLevel.UNKNOWN})
_INSPECTABLE_INFRASTRUCTURE = frozenset(
    {InfrastructureType.BRIDGE, InfrastructureType.ROAD, InfrastructureType.TUNNEL}
)
_ACTIONABLE_HAZARD_SEVERITIES = frozenset({HazardSeverity.HIGH, HazardSeverity.CRITICAL})

_HAZARD_SEVERITY_TO_PRIORITY: dict[HazardSeverity, RecommendationPriority] = {
    HazardSeverity.CRITICAL: RecommendationPriority.CRITICAL,
    HazardSeverity.HIGH: RecommendationPriority.HIGH,
}


def _has_incomplete_evidence(zone: SearchZone) -> bool:
    return bool(zone.missing_factors) or zone.uncertainty.level in _UNCERTAIN_EVIDENCE_LEVELS


def _recommendation_for_search_zone(
    zone: SearchZone,
    resources: list[Resource],
    capability_config: CapabilityMatchingConfig,
) -> Recommendation | None:
    if zone.priority_level not in _HIGH_PRIORITY_LEVELS:
        return None

    priority = (
        RecommendationPriority.CRITICAL
        if zone.priority_level == SearchPriorityLevel.CRITICAL
        else RecommendationPriority.HIGH
    )
    evidence_timestamp = (
        zone.supporting_evidence[0].timestamp if zone.supporting_evidence else datetime.now(UTC)
    )
    zone_evidence = Evidence(
        id=uuid4(),
        source_type=EvidenceSourceType.OBSERVATION,
        source="app.intelligence.search_priority",
        originating_subsystem="app.intelligence.search_priority",
        timestamp=evidence_timestamp,
        summary=(
            f"Search zone scored priority={zone.priority_level.value} "
            f"(score={zone.priority_score})."
        ),
        data_ref=str(zone.id),
    )
    supporting_evidence = [*zone.supporting_evidence, zone_evidence]

    if _has_incomplete_evidence(zone):
        return Recommendation(
            id=uuid4(),
            action=RecommendationAction.DEPLOY_DRONE_RECON,
            target_id=zone.id,
            target_description=f"Search zone (priority: {zone.priority_level.value})",
            priority=priority,
            rationale=(
                f"High-priority search zone (score={zone.priority_score}) with incomplete or "
                "uncertain evidence "
                f"({', '.join(zone.missing_factors) or zone.uncertainty.level.value}) "
                "— reconnaissance recommended before committing a ground team."
            ),
            required_capabilities=[ResourceCapability.AERIAL_RECON],
            supporting_evidence=supporting_evidence,
            uncertainty=zone.uncertainty,
            limitations=[
                "This recommendation does not verify drone availability or airspace conditions.",
            ],
            is_simulated=zone.is_simulated,
        )

    candidates = rank_candidates(
        required_capabilities=[ResourceCapability.GROUND_SEARCH],
        target_geometry=zone.geometry,
        target_geometry_crs=zone.geometry_crs,
        resources=resources,
        config=capability_config,
    )
    eligible = [c for c in candidates if c.eligible]

    if eligible:
        best = eligible[0]
        return Recommendation(
            id=uuid4(),
            action=RecommendationAction.DEPLOY_GROUND_SEARCH_TEAM,
            target_id=zone.id,
            target_description=f"Search zone (priority: {zone.priority_level.value})",
            priority=priority,
            rationale=(
                f"High-priority search zone (score={zone.priority_score}) with sufficient "
                "evidence. "
                f"Resource {best.resource_id} is capable, available, and reachable "
                f"(match_score={best.match_score})."
            ),
            required_capabilities=[ResourceCapability.GROUND_SEARCH],
            supporting_evidence=supporting_evidence,
            uncertainty=zone.uncertainty,
            limitations=list(best.rationale) if best.reachability.value == "unknown" else [],
            is_simulated=zone.is_simulated,
        )

    return Recommendation(
        id=uuid4(),
        action=RecommendationAction.ESCALATE_FOR_ADDITIONAL_RESOURCES,
        target_id=zone.id,
        target_description=f"Search zone (priority: {zone.priority_level.value})",
        priority=priority,
        rationale=(
            f"High-priority search zone (score={zone.priority_score}) has no currently eligible "
            "resource (capability, availability, or reachability gate failed for every candidate)."
        ),
        required_capabilities=[ResourceCapability.GROUND_SEARCH],
        supporting_evidence=supporting_evidence,
        uncertainty=zone.uncertainty,
        limitations=["No eligible resource was found among the resources considered."],
        is_simulated=zone.is_simulated,
    )


def _recommendation_for_infrastructure(
    infrastructure: Infrastructure, has_critical_zone: bool
) -> Recommendation | None:
    if infrastructure.type not in _INSPECTABLE_INFRASTRUCTURE:
        return None
    if infrastructure.status == InfrastructureStatus.OPERATIONAL:
        return None

    if infrastructure.status == InfrastructureStatus.NON_OPERATIONAL:
        priority = (
            RecommendationPriority.CRITICAL if has_critical_zone else RecommendationPriority.HIGH
        )
    else:  # DEGRADED or UNKNOWN
        priority = (
            RecommendationPriority.HIGH if has_critical_zone else RecommendationPriority.MODERATE
        )

    return Recommendation(
        id=uuid4(),
        action=RecommendationAction.INSPECT_INFRASTRUCTURE_BEFORE_DISPATCH,
        target_id=infrastructure.id,
        target_description=f"{infrastructure.type.value} (status: {infrastructure.status.value})",
        priority=priority,
        rationale=(
            f"{infrastructure.type.value.capitalize()} status is '{infrastructure.status.value}' — "
            "inspect before routing response resources across or through it."
        ),
        required_capabilities=[ResourceCapability.STRUCTURAL_ASSESSMENT],
        supporting_evidence=list(infrastructure.evidence),
        uncertainty=infrastructure.uncertainty,
        limitations=[
            "Status is based on the latest available observation, which may be outdated."
        ],
        is_simulated=infrastructure.is_simulated,
    )


def _recommendation_for_hazard(hazard: Hazard) -> Recommendation | None:
    if hazard.severity not in _ACTIONABLE_HAZARD_SEVERITIES:
        return None

    return Recommendation(
        id=uuid4(),
        action=RecommendationAction.AVOID_ROUTE_DUE_TO_HAZARD,
        target_id=hazard.id,
        target_description=f"{hazard.type.value} (severity: {hazard.severity.value})",
        priority=_HAZARD_SEVERITY_TO_PRIORITY[hazard.severity],
        rationale=(
            f"Active {hazard.type.value} hazard at severity '{hazard.severity.value}' — "
            "avoid routing through this area."
        ),
        required_capabilities=[],
        supporting_evidence=list(hazard.evidence),
        uncertainty=hazard.uncertainty,
        limitations=["Hazard extent/severity is based on the latest available observation."],
        is_simulated=hazard.is_simulated,
    )


def _hold_recommendation(is_simulated: bool) -> Recommendation:
    return Recommendation(
        id=uuid4(),
        action=RecommendationAction.HOLD_PENDING_MORE_INFORMATION,
        target_id=uuid4(),
        target_description=(
            "No specific target — insufficient data for an actionable recommendation."
        ),
        priority=RecommendationPriority.LOW,
        rationale=(
            "No search zone, hazard, or infrastructure record currently meets this "
            "engine's action thresholds."
        ),
        required_capabilities=[],
        supporting_evidence=[],
        uncertainty=Uncertainty(
            level=UncertaintyLevel.HIGH,
            confidence=None,
            reason="No actionable input data was available when recommendations were generated.",
            missing_information=[
                "search zones, hazards, or infrastructure records above the action threshold"
            ],
        ),
        limitations=[
            "This is a placeholder indicating no action is currently warranted, "
            "not an assessment of safety."
        ],
        is_simulated=is_simulated,
    )


_PRIORITY_RANK: dict[RecommendationPriority, int] = {
    RecommendationPriority.CRITICAL: 3,
    RecommendationPriority.HIGH: 2,
    RecommendationPriority.MODERATE: 1,
    RecommendationPriority.LOW: 0,
}


def rank_recommendations(recommendations: list[Recommendation]) -> list[Recommendation]:
    """Descending by priority — ties broken by id for a stable,
    deterministic order across repeated calls."""
    return sorted(
        recommendations, key=lambda r: (-_PRIORITY_RANK[r.priority], str(r.id))
    )


def generate_recommendations(
    search_zones: list[SearchZone],
    hazards: list[Hazard],
    infrastructure: list[Infrastructure],
    resources: list[Resource],
    capability_config: CapabilityMatchingConfig,
    *,
    is_simulated: bool = False,
) -> list[Recommendation]:
    """The full Phase 5 pipeline: apply every rule to every relevant
    input, then rank. Deterministic — calling this twice with the same
    inputs produces the same output (aside from fresh `id`/`uuid4()`
    values on each `Evidence`/`Recommendation`, matching the rest of this
    package's convention — see `search_priority.score_search_zone`)."""
    has_critical_zone = any(z.priority_level == SearchPriorityLevel.CRITICAL for z in search_zones)

    recommendations: list[Recommendation] = []
    for zone in search_zones:
        rec = _recommendation_for_search_zone(zone, resources, capability_config)
        if rec is not None:
            recommendations.append(rec)
    for item in infrastructure:
        rec = _recommendation_for_infrastructure(item, has_critical_zone)
        if rec is not None:
            recommendations.append(rec)
    for hazard in hazards:
        rec = _recommendation_for_hazard(hazard)
        if rec is not None:
            recommendations.append(rec)

    if not recommendations:
        recommendations.append(_hold_recommendation(is_simulated))

    return rank_recommendations(recommendations)

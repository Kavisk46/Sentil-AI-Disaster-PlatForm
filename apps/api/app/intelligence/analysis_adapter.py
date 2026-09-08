"""**F3**: adapts the existing analysis pipeline's real outputs into F2's
domain vocabulary (`DisasterScenario`), so the deterministic search-
priority/capability-matching/recommendation engines built in F2 can run
against real analysis data — not just the demo scenario.

    Analysis (app.ml / app.services)
        -> DamageAnalysis + list[BuildingDamage] + RoadRiskResponse   [real, existing]
        -> build_context_from_analysis()                              [this file]
        -> DisasterScenario                                            [F2, unmodified]
        -> IntelligenceService.score_search_zones/build_recommendations [F2, unmodified]

This is an **adapter, not a second pipeline**: it introduces no new
scoring/matching/recommendation logic, no new geometry system, and no
new damage taxonomy — it only maps already-real, already-typed domain
objects (`BuildingDamage`, `RoadEdge`) into F2's `AffectedArea`/
`Infrastructure` shapes. `Hazard`s and `Route`s are left empty by this
adapter (no hazard-detection system and no pre-computed routes exist for
an analysis) — never fabricated to make the scenario look complete.

**Resources are not real** — no resource-ingestion system exists
anywhere in this codebase (confirmed in the F2 architecture audit).
`build_context_from_analysis()` reuses the F2 demo scenario's resource
pool, each already carrying `is_simulated=True` from `demo_scenario.py`
— never silently presented as real telemetry. See
`docs/architecture/intelligence.md`, "F3: analysis-derived intelligence,"
for the full rationale, including why this is not a case of blurring
demo and real data: the *search zones* this adapter produces are real
(`is_simulated=False`, built from real `BuildingDamage`), while the
*resources* matched against them are simulated — both facts are carried
independently on each object and must be surfaced independently by any
caller (see `app/schemas/analysis_intelligence.py`).
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from app.intelligence.demo_scenario import build_demo_scenario
from app.intelligence.schemas import (
    AffectedArea,
    Disaster,
    DisasterStatus,
    DisasterType,
    Evidence,
    EvidenceSourceType,
    Infrastructure,
    InfrastructureStatus,
    InfrastructureType,
    Uncertainty,
    UncertaintyLevel,
)
from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.ml.geospatial.geometry import BoundingBoxGeometry
from app.ml.schemas import BuildingDamage, DamageAnalysis
from app.roads.schemas import RiskLevel, RoadEdge
from app.schemas.analysis import AnalysisErrorCode, AnalysisStatus
from app.schemas.road_risk import RoadRiskResponse
from app.services.intelligence_repository import DisasterScenario


class IntelligenceContextUnavailableReason(StrEnum):
    """Every reason `build_context_from_analysis` can decline to build a
    scenario — a closed, non-overlapping set (see the docstring on each
    branch in `build_context_from_analysis` for exactly when each one
    fires). Reuses `AnalysisErrorCode`'s own values for the two "the
    analysis itself failed" cases rather than inventing parallel ones."""

    ANALYSIS_NOT_COMPLETED = "ANALYSIS_NOT_COMPLETED"
    MODEL_UNAVAILABLE = AnalysisErrorCode.MODEL_UNAVAILABLE.value
    INFERENCE_FAILURE = AnalysisErrorCode.INFERENCE_FAILURE.value
    # Milestone F4 — reuses AnalysisErrorCode's own values for the same
    # reason MODEL_UNAVAILABLE/INFERENCE_FAILURE above already do: each
    # failure stays traceable to the exact pipeline stage that failed,
    # rather than collapsing every non-MODEL_UNAVAILABLE failure into the
    # single generic INFERENCE_FAILURE bucket.
    MODEL_LOAD_FAILURE = AnalysisErrorCode.MODEL_LOAD_FAILURE.value
    INVALID_IMAGE = AnalysisErrorCode.INVALID_IMAGE.value
    PREPROCESSING_FAILURE = AnalysisErrorCode.PREPROCESSING_FAILURE.value
    POSTPROCESSING_FAILURE = AnalysisErrorCode.POSTPROCESSING_FAILURE.value
    NO_GEOREFERENCE = "NO_GEOREFERENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class AnalysisContextResult:
    """The result of attempting to build a `DisasterScenario` from an
    analysis: either a real `scenario`, or a disclosed `unavailable_reason`
    — never both, never neither. Deliberately not a `DisasterScenario |
    None` union: a bare `None` return would force every caller to
    re-derive *why*, risking a second, drifting copy of this module's own
    gating logic."""

    __slots__ = ("scenario", "unavailable_reason")

    def __init__(
        self,
        scenario: DisasterScenario | None,
        unavailable_reason: IntelligenceContextUnavailableReason | None,
    ) -> None:
        if (scenario is None) == (unavailable_reason is None):
            raise ValueError("Exactly one of scenario/unavailable_reason must be set.")
        self.scenario = scenario
        self.unavailable_reason = unavailable_reason

    @property
    def available(self) -> bool:
        return self.scenario is not None


def derive_disaster_id(analysis_id: UUID) -> UUID:
    """A pure function of `analysis_id` — deterministic, not stored. This
    is the resolution of F3's identifier-design question: `analysis_id`
    and `disaster_id` remain genuinely distinct concepts (an analysis is
    one uploaded image; a disaster spans observations/hazards/resources/
    infrastructure), so this is not a rename. It's a reproducible
    derivation, computed fresh on every request (see
    `app.services.analysis_intelligence_service`, which never persists
    the resulting `Disaster`/`DisasterScenario` — the same "recompute,
    never cache" principle F2's own `IntelligenceService` already uses
    for `SearchZone`/`Recommendation`, applied one layer further out)."""
    return uuid5(NAMESPACE_URL, f"https://sentinelai.analysis/{analysis_id}")


def _is_georeferenced(building: BuildingDamage) -> bool:
    return (
        building.georeferenced
        and building.coordinate_reference_system is CoordinateReferenceSystem.WGS84
        and building.geometry is not None
    )


def _building_to_affected_area(building: BuildingDamage, analysis_id: UUID) -> AffectedArea:
    assert building.geometry is not None  # guaranteed by the _is_georeferenced filter above
    evidence = Evidence(
        id=uuid4(),
        source_type=EvidenceSourceType.DAMAGE_ANALYSIS,
        source=f"analysis:{analysis_id}",
        originating_subsystem="app.ml.inference",
        timestamp=datetime.now(UTC),
        summary=(
            f"Damage classifier detected '{building.damage_class.value}' "
            f"(confidence={building.confidence:.2f}) for building {building.building_id}."
        ),
        data_ref=building.building_id,
    )
    return AffectedArea(
        id=uuid5(NAMESPACE_URL, f"https://sentinelai.analysis/{analysis_id}/building/{building.building_id}"),
        geometry=building.geometry,
        geometry_crs=building.coordinate_reference_system,
        damage_level=building.damage_class,
        # No population source exists anywhere in this codebase — never estimated.
        affected_population=None,
        accessibility=None,
        evidence=[evidence],
        uncertainty=Uncertainty(
            level=_confidence_to_uncertainty_level(building.confidence),
            # A real per-building softmax confidence exists (`building.confidence`),
            # but AffectedArea/SearchZone uncertainty is deliberately kept
            # qualitative here too, matching every other Uncertainty in this
            # codebase — see app/intelligence/schemas.py's module docstring.
            confidence=None,
            reason=(
                f"Derived from a single damage-classification prediction "
                f"(confidence={building.confidence:.2f})."
            ),
            missing_information=["independent ground confirmation"],
        ),
        is_simulated=False,
    )


def _confidence_to_uncertainty_level(confidence: float) -> UncertaintyLevel:
    """A documented, deterministic mapping — not a calibrated
    probability. Thresholds mirror `Settings.INCIDENT_CONFIDENCE_*`'s
    spirit (high >= 0.8, moderate >= 0.5) without importing
    `app.incident` (F3 shouldn't couple `app.intelligence` to the
    AI-briefing subsystem for one threshold pair)."""
    if confidence >= 0.8:
        return UncertaintyLevel.LOW
    if confidence >= 0.5:
        return UncertaintyLevel.MODERATE
    return UncertaintyLevel.HIGH


_FAILURE_CODE_TO_UNAVAILABLE_REASON: dict[
    AnalysisErrorCode, IntelligenceContextUnavailableReason
] = {
    AnalysisErrorCode.MODEL_UNAVAILABLE: IntelligenceContextUnavailableReason.MODEL_UNAVAILABLE,
    AnalysisErrorCode.MODEL_LOAD_FAILURE: IntelligenceContextUnavailableReason.MODEL_LOAD_FAILURE,
    AnalysisErrorCode.INVALID_IMAGE: IntelligenceContextUnavailableReason.INVALID_IMAGE,
    AnalysisErrorCode.PREPROCESSING_FAILURE: (
        IntelligenceContextUnavailableReason.PREPROCESSING_FAILURE
    ),
    AnalysisErrorCode.POSTPROCESSING_FAILURE: (
        IntelligenceContextUnavailableReason.POSTPROCESSING_FAILURE
    ),
    AnalysisErrorCode.INFERENCE_FAILURE: IntelligenceContextUnavailableReason.INFERENCE_FAILURE,
}


_RISK_LEVEL_TO_INFRA_STATUS: dict[RiskLevel, InfrastructureStatus] = {
    RiskLevel.CRITICAL: InfrastructureStatus.NON_OPERATIONAL,
    RiskLevel.HIGH: InfrastructureStatus.DEGRADED,
    RiskLevel.MODERATE: InfrastructureStatus.DEGRADED,
    RiskLevel.LOW: InfrastructureStatus.OPERATIONAL,
}


def _edge_to_infrastructure(edge: RoadEdge, analysis_id: UUID) -> Infrastructure | None:
    """`None` for an edge with no real risk assessment (`risk_level is
    None`) or no accessibility signal worth reporting — never guesses an
    `InfrastructureStatus` from nothing."""
    if edge.risk_level is None:
        return None
    status = _RISK_LEVEL_TO_INFRA_STATUS[edge.risk_level]
    evidence = Evidence(
        id=uuid4(),
        source_type=EvidenceSourceType.ROAD_RISK_ANALYSIS,
        source=f"analysis:{analysis_id}",
        originating_subsystem="app.risk.analyzer",
        timestamp=datetime.now(UTC),
        summary=(
            f"Road segment '{edge.name or f'{edge.source_node}->{edge.target_node}'}' "
            f"assessed at risk_level={edge.risk_level.value}."
        ),
        data_ref=f"{edge.source_node}->{edge.target_node}",
    )
    # RoadEdge carries no standalone Point geometry — only node ids (see
    # app/roads/schemas.py). This adapter does not fabricate one; the
    # edge's real coordinates are only ever available via a computed
    # RouteResult.route_geometry (see analysis_intelligence_service.py's
    # route-feasibility step), never invented here.
    return Infrastructure(
        id=uuid5(
            NAMESPACE_URL,
            f"https://sentinelai.analysis/{analysis_id}/edge/{edge.source_node}-{edge.target_node}",
        ),
        type=InfrastructureType.ROAD,
        # A degenerate (zero-area) box is an honest placeholder for "this
        # edge has no independently-known point geometry" while still
        # satisfying Infrastructure.geometry's required Geometry type —
        # never a real-looking but invented coordinate. Callers must
        # treat a zero-area BoundingBoxGeometry as non-renderable, the
        # same way command-map.tsx already treats untagged/IMAGE geometry.
        geometry=BoundingBoxGeometry(coordinates=(0.0, 0.0, 0.0, 0.0)),
        geometry_crs=CoordinateReferenceSystem.IMAGE,
        status=status,
        accessibility=edge.accessibility,
        evidence=[evidence],
        uncertainty=Uncertainty(
            level=UncertaintyLevel.MODERATE,
            confidence=None,
            reason=(
                "Derived from the road-risk formula's proximity-based estimate, "
                "not a verified inspection."
            ),
            missing_information=["field inspection"],
        ),
        is_simulated=False,
    )


def build_context_from_analysis(
    analysis: DamageAnalysis,
    buildings: list[BuildingDamage],
    road_risk: RoadRiskResponse,
) -> AnalysisContextResult:
    """The core F3 adapter. Pure function of already-fetched domain
    objects — never touches a repository or the HTTP layer itself (see
    the module docstring, "consume domain-level information, not raw
    HTTP responses").

    Gating, in order, each with its own distinct reason (never collapsed
    into one generic "unavailable"):

    1. `analysis.status` isn't `COMPLETED` -> `ANALYSIS_NOT_COMPLETED`,
       or, if it's `FAILED`, the real `analysis.failure.code`
       (Milestone F4: any of `MODEL_UNAVAILABLE`/`MODEL_LOAD_FAILURE`/
       `INVALID_IMAGE`/`PREPROCESSING_FAILURE`/`POSTPROCESSING_FAILURE`/
       `INFERENCE_FAILURE`) instead — never collapsed into one generic
       reason.
    2. Zero buildings at all -> `INSUFFICIENT_EVIDENCE`.
    3. Buildings exist but none are georeferenced (WGS84) ->
       `NO_GEOREFERENCE` — the honest, common state today (see
       `apps/api/README.md`, "Image-space mode").
    4. Otherwise: a real `DisasterScenario`, `is_simulated=False`, built
       from every georeferenced building. Road-derived `Infrastructure`
       is included only when `road_risk.available` — never fabricated
       when roads are unavailable (that's a separate, independently
       disclosed capability; see `analysis_intelligence_service.py`).
    """
    if analysis.status is not AnalysisStatus.COMPLETED:
        if analysis.status is AnalysisStatus.FAILED and analysis.failure is not None:
            reason = _FAILURE_CODE_TO_UNAVAILABLE_REASON.get(
                analysis.failure.code, IntelligenceContextUnavailableReason.INFERENCE_FAILURE
            )
        else:
            reason = IntelligenceContextUnavailableReason.ANALYSIS_NOT_COMPLETED
        return AnalysisContextResult(scenario=None, unavailable_reason=reason)

    if not buildings:
        return AnalysisContextResult(
            scenario=None,
            unavailable_reason=IntelligenceContextUnavailableReason.INSUFFICIENT_EVIDENCE,
        )

    georeferenced = [b for b in buildings if _is_georeferenced(b)]
    if not georeferenced:
        return AnalysisContextResult(
            scenario=None, unavailable_reason=IntelligenceContextUnavailableReason.NO_GEOREFERENCE
        )

    disaster_id = derive_disaster_id(analysis.analysis_id)
    affected_areas = tuple(
        _building_to_affected_area(b, analysis.analysis_id) for b in georeferenced
    )

    infrastructure: tuple[Infrastructure, ...] = ()
    if road_risk.available:
        mapped = [_edge_to_infrastructure(e, analysis.analysis_id) for e in road_risk.edges]
        infrastructure = tuple(i for i in mapped if i is not None)

    # No real resource-ingestion system exists anywhere in this codebase
    # (see module docstring) — reuse the F2 demo pool, whose entries are
    # already correctly tagged is_simulated=True. Never invented fresh.
    demo_resources = build_demo_scenario().resources

    disaster = Disaster(
        id=disaster_id,
        type=DisasterType.OTHER,
        label=f"Analysis {analysis.analysis_id}",
        status=DisasterStatus.ACTIVE,
        location=None,
        start_time=analysis.created_at,
        source=f"analysis:{analysis.analysis_id}",
        is_simulated=False,
        provenance=(
            f"Derived from real analysis {analysis.analysis_id}'s damage classification "
            "and road-risk results — see app.intelligence.analysis_adapter."
        ),
    )

    scenario = DisasterScenario(
        disaster=disaster,
        observations=(),
        affected_areas=affected_areas,
        hazards=(),  # no hazard-detection system exists — never fabricated
        resources=demo_resources,
        rescue_teams=(),
        infrastructure=infrastructure,
        routes=(),  # computed on demand, not pre-populated — see route-feasibility step
    )
    return AnalysisContextResult(scenario=scenario, unavailable_reason=None)

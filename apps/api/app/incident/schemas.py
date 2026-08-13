"""Typed contracts for incident intelligence: the structured input an LLM
(or the deterministic fallback) receives (`IncidentContext`), the only
thing an `LLMProvider` is trusted to produce (`LLMNarrativeOutput`), and
the final, client-facing result (`IncidentBriefing`).

Reuses existing result types directly rather than re-deriving them:
`DamageSummary` (`app.ml.schemas`), `RiskLevel` (`app.roads.schemas`),
`RoutingMode` (`app.routing.schemas`) — no parallel taxonomy.
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.ml.geospatial.geometry import BoundingBoxGeometry
from app.ml.schemas import DamageSummary
from app.roads.schemas import RiskLevel
from app.routing.schemas import RoutingMode
from app.schemas.analysis import AnalysisStatus


class IncidentSeverity(StrEnum):
    """A deterministic classification of overall incident severity —
    computed by `app.incident.severity.classify_incident_severity()` from
    real damage counts, **never** taken from LLM output. Engineering
    categories, not a validated emergency-management severity scale — see
    `app.incident.severity` for the exact thresholds and their rationale.
    """

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class ConfidenceLevel(StrEnum):
    """A deterministic classification of the underlying damage detections'
    average confidence — computed by
    `app.incident.severity.classify_confidence()`, **never** an LLM's
    self-reported confidence. See "Confidence and uncertainty" in
    apps/api/README.md for why: an LLM's stated confidence is not
    evidence of anything; this is derived from real model output
    (`BuildingDamage.confidence`) instead.
    """

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    UNKNOWN = "unknown"


class AffectedStructuresSummary(BaseModel):
    """A thin, briefing-facing wrapper over `DamageSummary` — kept as its
    own type only so the briefing schema doesn't need to import a
    `DamageSummary` field name (`total_buildings`) that reads oddly next
    to "structures" elsewhere in this package's vocabulary. Values are
    copied 1:1 from `DamageSummary`, never recomputed."""

    total: int = Field(ge=0)
    damaged: int = Field(ge=0)
    severely_damaged: int = Field(ge=0)
    destroyed: int = Field(ge=0)
    high_priority_count: int = Field(ge=0)

    @classmethod
    def from_damage_summary(
        cls, summary: DamageSummary, high_priority_count: int
    ) -> "AffectedStructuresSummary":
        return cls(
            total=summary.total_buildings,
            damaged=summary.damaged_buildings,
            severely_damaged=summary.severely_damaged,
            destroyed=summary.destroyed,
            high_priority_count=high_priority_count,
        )


class DamageContext(BaseModel):
    """Damage-analysis input to incident intelligence. `available=False`
    (analysis not `completed` yet) means every other field stays at its
    empty default — never a fabricated count."""

    available: bool
    reason: str | None = None
    summary: DamageSummary | None = None
    average_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Mean BuildingDamage.confidence across all buildings.",
    )
    high_priority_structure_ids: list[str] = Field(default_factory=list)
    spatial_bounds: BoundingBoxGeometry | None = Field(
        default=None, description="Bounding box over georeferenced buildings only, if any exist."
    )


class RoadRiskContext(BaseModel):
    """Road-risk input to incident intelligence — see
    `app.services.road_risk_service.RoadRiskService` for what
    `available=False` means (analysis not completed, no georeferenced
    damage, or no road network loaded)."""

    available: bool
    reason: str | None = None
    total_edges_assessed: int = 0
    risky_edge_count: int = Field(default=0, description="Edges at RiskLevel.HIGH or .CRITICAL.")
    blocked_edge_count: int = 0
    restricted_edge_count: int = 0
    highest_risk_level: RiskLevel | None = None
    sample_risk_source_building_ids: list[str] = Field(default_factory=list)


class RouteContext(BaseModel):
    """Routing input to incident intelligence — only populated when the
    caller explicitly requested route context (see
    `app.schemas.incident.RouteQuery`); routing needs a start/destination
    this package has no way to invent. `selected_*` always refers to the
    `risk_aware` route; `baseline_*` to `distance_only` — the same
    convention `app.routing.schemas.RouteComparison` already uses."""

    available: bool
    reason: str | None = None
    selected_mode: RoutingMode | None = None
    selected_distance_meters: float | None = None
    selected_risk_score: float | None = None
    baseline_distance_meters: float | None = None
    baseline_risk_score: float | None = None
    detour_ratio: float | None = None
    avoided_high_risk_segment_count: int = 0


class IncidentContext(BaseModel):
    """Everything an `LLMProvider` (or the deterministic fallback) may
    draw on — nothing else. Deliberately contains no free text a user
    controls (no filenames, no arbitrary strings) — see
    `app.incident`, "Prompt injection defense"."""

    analysis_id: UUID
    analysis_status: AnalysisStatus
    damage: DamageContext
    road_risk: RoadRiskContext
    route: RouteContext
    generated_at: datetime


class LLMNarrativeOutput(BaseModel):
    """The **only** thing an `LLMProvider` is trusted to produce — four
    free-text synthesis fields. Deliberately excludes
    `incident_severity`/`confidence`/`affected_structures`: those are
    always computed deterministically by
    `app.incident.severity`/`app.incident.briefing_builder`, never taken
    from LLM output, even if a misbehaving provider includes them in its
    JSON (`model_validate` simply ignores unrecognized/extra keys by
    default — see `app.incident.validator`).
    """

    priority_area: str
    route_summary: str
    key_findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class IncidentBriefing(BaseModel):
    """The final, client-facing result of `GET`/`POST
    /api/v1/analysis/{analysis_id}/summary`."""

    analysis_id: UUID
    incident_severity: IncidentSeverity
    affected_structures: AffectedStructuresSummary
    priority_area: str
    route_summary: str
    key_findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel
    generated_at: datetime
    source: Literal["provider", "fallback"] = Field(
        description=(
            "'provider': the configured LLMProvider's output passed validation and "
            "grounding (this may itself be the deterministic provider, not necessarily "
            "an LLM). 'fallback': the configured provider failed, timed out, returned "
            "malformed output, or made an unsupported claim, so the service's own "
            "template-based safety net produced this narrative instead."
        )
    )
    prompt_version: str
    disclaimer: str = Field(
        description="A fixed safety disclaimer, always set server-side — never LLM-generated."
    )

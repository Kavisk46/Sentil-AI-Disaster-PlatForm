"""Route-facing response contracts for
`/api/v1/analysis/{analysis_id}/intelligence[...]` (F3).

Thin wrappers around `app.intelligence.schemas` domain types, the same
convention `app.schemas.intelligence` (F2) already established — reused
directly here, not duplicated. Every response distinguishes three
independent facts, per the F3 brief ("must clearly distinguish: available
data, unavailable data, simulated data"):

1. **`context_available`/`context_unavailable_reason`** — whether enough
   real analysis data exists to build search zones at all (see
   `app.intelligence.analysis_adapter.IntelligenceContextUnavailableReason`).
2. **`roads_available`/`roads_unavailable_reason`** — a separate,
   independent gate: search zones can be available while roads are not.
3. **`resources_are_demo`** — always `True` in F3 (no real resource
   ingestion system exists yet — see `app.intelligence.analysis_adapter`);
   carried explicitly so no caller can mistake matched resources for real
   telemetry.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from app.intelligence.schemas import CapabilityMatchResult, Recommendation, SearchZone
from app.routing.schemas import RouteResult


class RouteFeasibilityStatus(BaseModel):
    """Whether a real route was actually computed for a capability-match
    candidate, and why not when it wasn't. Never a fabricated route."""

    status: str = Field(
        description=(
            "'computed' (a real RouteResult was obtained, which may itself have "
            "found=false), 'route_unavailable' (roads not loaded, or a location "
            "isn't a tagged WGS84 coordinate), or 'not_applicable' (the candidate "
            "failed an earlier gate, so route feasibility was never checked)."
        )
    )
    reason: str | None = None


class AnalysisCapabilityMatch(BaseModel):
    """One resource's F2 capability-match result, optionally enriched
    with a real, computed route (never invented geometry) — see
    `app.services.analysis_intelligence_service`, "Route feasibility"."""

    match: CapabilityMatchResult
    route: RouteResult | None = None
    route_feasibility: RouteFeasibilityStatus


class AnalysisIntelligenceContextResponse(BaseModel):
    """`GET /api/v1/analysis/{analysis_id}/intelligence`."""

    analysis_id: UUID
    disaster_id: UUID = Field(
        description=(
            "Deterministically derived from analysis_id — see "
            "app.intelligence.analysis_adapter.derive_disaster_id. Not a stored foreign key."
        )
    )
    context_available: bool
    context_unavailable_reason: str | None = None
    is_simulated: bool = Field(
        description="Always False on this path — real analysis-derived data."
    )
    affected_area_count: int = 0
    hazard_count: int = 0
    infrastructure_count: int = 0
    roads_available: bool
    roads_unavailable_reason: str | None = None
    resources_available: bool
    resources_are_demo: bool


class AnalysisSearchZonesResponse(BaseModel):
    """`GET /api/v1/analysis/{analysis_id}/intelligence/search-zones`."""

    analysis_id: UUID
    disaster_id: UUID
    context_available: bool
    context_unavailable_reason: str | None = None
    search_zones: list[SearchZone] = Field(default_factory=list)


class AnalysisRecommendationsResponse(BaseModel):
    """`GET /api/v1/analysis/{analysis_id}/intelligence/recommendations`.

    Bundles ranked recommendations with resource-capability-match detail
    for the single top-priority search zone (deliberately not a separate
    endpoint — "Only create endpoints that are actually justified"),
    directly serving the "What can reach it?" question.
    """

    analysis_id: UUID
    disaster_id: UUID
    context_available: bool
    context_unavailable_reason: str | None = None
    recommendations: list[Recommendation] = Field(default_factory=list)
    top_search_zone_id: UUID | None = None
    resource_candidates: list[AnalysisCapabilityMatch] = Field(default_factory=list)
    resources_are_demo: bool
    roads_available: bool
    roads_unavailable_reason: str | None = None

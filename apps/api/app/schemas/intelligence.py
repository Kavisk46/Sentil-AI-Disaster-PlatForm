"""Route-facing response contracts for `/api/v1/intelligence/*`.

Thin wrappers around `app.intelligence.schemas` domain types — mirrors
`app.schemas.roads`/`app.schemas.road_risk` importing their domain types
from `app.roads`/`app.risk` rather than redefining them. Every endpoint
scoped to one `disaster_id` raises `DisasterNotFoundError` (-> `404`, see
`app/api/exception_handlers.py`) when it's unknown — there is no
`available`/`reason` field on these responses because the *only*
"unavailable" condition at this layer is "no such disaster," which a 404
already represents cleanly; an empty `search_zones`/`resources`/
`recommendations` list for a *known* disaster with no recorded data is a
real, valid state, not an error.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from app.intelligence.schemas import Disaster, Recommendation, Resource, SearchZone


class DisasterSummaryResponse(BaseModel):
    """`GET /api/v1/intelligence/{disaster_id}`."""

    disaster: Disaster
    observation_count: int = Field(ge=0)
    affected_area_count: int = Field(ge=0)
    hazard_count: int = Field(ge=0)
    resource_count: int = Field(ge=0)
    infrastructure_count: int = Field(ge=0)
    route_count: int = Field(ge=0)


class SearchZoneListResponse(BaseModel):
    """`GET /api/v1/intelligence/{disaster_id}/search-zones` — ranked
    descending by `priority_score`."""

    disaster_id: UUID
    search_zones: list[SearchZone] = Field(default_factory=list)


class ResourceListResponse(BaseModel):
    """`GET /api/v1/intelligence/{disaster_id}/resources` — the raw
    resource registry for this disaster, unranked (ranking is
    target-specific — see `app.intelligence.capability_matching`, used
    internally by the recommendations endpoint)."""

    disaster_id: UUID
    resources: list[Resource] = Field(default_factory=list)


class RecommendationListResponse(BaseModel):
    """`GET /api/v1/intelligence/{disaster_id}/recommendations` — ranked
    descending by priority."""

    disaster_id: UUID
    recommendations: list[Recommendation] = Field(default_factory=list)

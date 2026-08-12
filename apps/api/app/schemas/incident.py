"""Request schema for `POST /api/v1/analysis/{analysis_id}/summary`."""

from pydantic import BaseModel

from app.roads.schemas import GeographicCoordinate


class RouteQuery(BaseModel):
    """Optional start/destination to enrich a briefing with routing
    context (`app.incident.schemas.RouteContext`) — reuses the same
    validated WGS84 coordinate type `POST /api/v1/routing` uses. No
    `mode`: the briefing always compares `risk_aware` (the "selected"
    route) against `distance_only` (the baseline), the same convention
    `RouteComparison` already establishes."""

    start: GeographicCoordinate
    destination: GeographicCoordinate


class IncidentSummaryRequest(BaseModel):
    """`POST /api/v1/analysis/{analysis_id}/summary` body — entirely
    optional; an empty/absent body regenerates the summary with damage
    and road-risk context only, same as `GET` on the same path."""

    route: RouteQuery | None = None

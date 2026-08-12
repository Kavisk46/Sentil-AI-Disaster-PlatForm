"""Typed contracts for a routing result.

`RouteResult.edge_sequence` reuses `app.roads.schemas.RoadEdge` directly —
no second, parallel edge type — so a route's segments carry the exact same
`base_cost`/`risk_score`/`risk_level`/`accessibility` fields already
established (Milestones 6A/6B), not a re-derived summary of them.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

from app.ml.geospatial.geometry import Coordinate
from app.roads.schemas import RoadEdge


class RoutingMode(StrEnum):
    """`distance_only` minimizes `RoadEdge.base_cost` alone — the control
    condition. `risk_aware` minimizes a risk-adjusted cost (see
    `app.routing.cost`). See `app.routing` for the full rationale."""

    DISTANCE_ONLY = "distance_only"
    RISK_AWARE = "risk_aware"


class AccessibilitySummary(BaseModel):
    """How many of a route's segments fall into each `AccessibilityStatus`
    — `blocked` should always be `0` for any successfully found route,
    since blocked edges are excluded from the search entirely (see
    `app.routing.cost`); reported anyway for a defensive, honest count
    rather than an assumption."""

    open: int = 0
    restricted: int = 0
    blocked: int = 0
    unknown: int = 0


class RouteResult(BaseModel):
    """The result of one routing request in one mode.

    `found=False` is a **structured result, not a missing/empty one** —
    every list field stays `[]` and every optional scalar stays `None`,
    with `reason` explaining why (no path exists, no road network is
    loaded, no node was found near the requested coordinates, ...). Never
    silently returns an empty *successful* route.
    """

    routing_mode: RoutingMode
    found: bool
    start_node: str | None = None
    destination_node: str | None = None
    node_sequence: list[str] = Field(default_factory=list)
    edge_sequence: list[RoadEdge] = Field(default_factory=list)
    route_geometry: list[Coordinate] = Field(
        default_factory=list,
        description="Ordered (longitude, latitude) points along the route, one per visited node.",
    )
    total_distance: float | None = Field(
        default=None,
        description="Meters — sum of edge_sequence's real distances, mode-independent.",
    )
    total_cost: float | None = Field(
        default=None,
        description="Sum of the mode-specific edge cost actually minimized (app.routing.cost).",
    )
    accumulated_risk: float | None = Field(
        default=None,
        description=(
            "Sum of edge_sequence's risk_score. None when risk data was never assessed for this "
            "route (e.g. distance_only routing without an available risk analysis) — distinct from "
            "0.0, which means risk was assessed and genuinely found nothing nearby."
        ),
    )
    number_of_edges: int = 0
    accessibility_summary: AccessibilitySummary = Field(default_factory=AccessibilitySummary)
    reason: str | None = Field(
        default=None,
        description="Explains why found=False, or why data (e.g. risk) is unavailable.",
    )


class RouteComparison(BaseModel):
    """`distance_only` vs `risk_aware` for the same start/destination/road
    graph — see `app.routing`, "Route comparison," for the full
    methodology. Every field here is purely descriptive: nothing in this
    schema feeds back into route selection.
    """

    distance_only: RouteResult
    risk_aware: RouteResult
    distance_difference: float | None = Field(
        default=None,
        description="risk_aware.total_distance - distance_only.total_distance (meters).",
    )
    risk_difference: float | None = Field(
        default=None,
        description="risk_aware.accumulated_risk - distance_only.accumulated_risk.",
    )
    routes_differ: bool = False
    detour_ratio: float | None = Field(
        default=None,
        description="risk_aware.total_distance / distance_only.total_distance.",
    )
    risky_segments_distance_only: int = 0
    risky_segments_risk_aware: int = 0
    blocked_segments_in_graph: int = 0
    high_risk_edges_avoided: list[str] = Field(
        default_factory=list,
        description=(
            "'source->target' edges at HIGH/CRITICAL risk that distance_only used and "
            "risk_aware did not."
        ),
    )

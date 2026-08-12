"""Turns a successful `app.routing.algorithm.PathResult` into the
API-facing `RouteResult` — pure data reshaping, no repository access.
`RoutingService` handles the `found=False` case itself (it already has
`start_node`/`destination_node` in hand from nearest-node resolution,
which `PathResult` alone doesn't carry).
"""

from collections import Counter
from collections.abc import Mapping, Sequence

from app.roads.schemas import AccessibilityStatus, RoadEdge, RoadNode
from app.routing.algorithm import PathResult
from app.routing.schemas import AccessibilitySummary, RouteResult, RoutingMode


def build_route_result(
    path: PathResult, mode: RoutingMode, nodes_by_id: Mapping[str, RoadNode]
) -> RouteResult:
    """Assumes `path.found` is `True` — callers check that first."""
    total_distance = sum(edge.distance for edge in path.edge_sequence)
    accumulated_risk = _accumulated_risk(path.edge_sequence)
    route_geometry = [
        nodes_by_id[node_id].geometry.coordinates
        for node_id in path.node_sequence
        if node_id in nodes_by_id
    ]

    return RouteResult(
        routing_mode=mode,
        found=True,
        start_node=path.node_sequence[0],
        destination_node=path.node_sequence[-1],
        node_sequence=path.node_sequence,
        edge_sequence=path.edge_sequence,
        route_geometry=route_geometry,
        total_distance=total_distance,
        total_cost=path.total_cost,
        accumulated_risk=accumulated_risk,
        number_of_edges=len(path.edge_sequence),
        accessibility_summary=summarize_accessibility(path.edge_sequence),
        reason=None,
    )


def _accumulated_risk(edges: Sequence[RoadEdge]) -> float | None:
    """`None` if risk was never assessed for any segment of the route (a
    `distance_only` route computed without an available risk analysis) —
    `0.0` (not `None`) for the trivial start==destination route, which
    has no segments to be risky at all."""
    if not edges:
        return 0.0
    if not any(edge.risk_score is not None for edge in edges):
        return None
    return sum(edge.risk_score or 0.0 for edge in edges)


def summarize_accessibility(edges: Sequence[RoadEdge]) -> AccessibilitySummary:
    counts = Counter(edge.accessibility for edge in edges)
    return AccessibilitySummary(
        open=counts.get(AccessibilityStatus.OPEN, 0),
        restricted=counts.get(AccessibilityStatus.RESTRICTED, 0),
        blocked=counts.get(AccessibilityStatus.BLOCKED, 0),
        unknown=counts.get(AccessibilityStatus.UNKNOWN, 0),
    )

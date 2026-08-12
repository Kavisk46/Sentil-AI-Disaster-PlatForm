"""Derived, purely descriptive research metrics — computed *after* a route
already exists, never influencing route selection (that's
`app.routing.cost`'s job). Supports the "Route comparison"/"Research
metrics" requirements: route distance and risk are already first-class
`RouteResult` fields; this module adds the remaining ones (risky-segment
counts, blocked-edge counts, detour ratio, and which specific high-risk
edges a safer route avoided) for explainability and research evaluation.
"""

from collections.abc import Sequence

from app.roads.schemas import AccessibilityStatus, RiskLevel, RoadEdge
from app.routing.schemas import RouteResult

_RISKY_LEVELS = frozenset({RiskLevel.HIGH, RiskLevel.CRITICAL})


def count_risky_segments(route: RouteResult) -> int:
    """Segments in `route` at `RiskLevel.HIGH` or `.CRITICAL`."""
    return sum(1 for edge in route.edge_sequence if edge.risk_level in _RISKY_LEVELS)


def count_blocked_edges(edges: Sequence[RoadEdge]) -> int:
    """Blocked edges present in the graph a route was searched over.
    Every one of them was, by construction, excluded from any resulting
    route (see `app.routing.cost`) — this reports how many existed to be
    avoided, not a claim about a specific counterfactual detour distance.
    """
    return sum(1 for edge in edges if edge.accessibility is AccessibilityStatus.BLOCKED)


def detour_ratio(
    risk_aware_distance: float | None, distance_only_distance: float | None
) -> float | None:
    """`risk_aware_distance / distance_only_distance` — exactly the
    formula the milestone specifies. `None` if either distance is
    unavailable or the baseline distance is zero (nothing to divide by) —
    never a fabricated ratio."""
    if risk_aware_distance is None or distance_only_distance is None or distance_only_distance == 0:
        return None
    return risk_aware_distance / distance_only_distance


def high_risk_edges_avoided(distance_only: RouteResult, risk_aware: RouteResult) -> list[str]:
    """`"source->target"` edges the `distance_only` route used at
    `HIGH`/`CRITICAL` risk that the `risk_aware` route did not — the
    concrete, explainable answer to "why did the risk-aware route
    detour?". Empty if either route wasn't found, or if `distance_only`'s
    edges were never risk-assessed (`risk_level` is `None` on all of
    them) — never guessed.
    """
    if not (distance_only.found and risk_aware.found):
        return []
    risk_aware_ids = {(edge.source_node, edge.target_node) for edge in risk_aware.edge_sequence}
    return [
        f"{edge.source_node}->{edge.target_node}"
        for edge in distance_only.edge_sequence
        if edge.risk_level in _RISKY_LEVELS
        and (edge.source_node, edge.target_node) not in risk_aware_ids
    ]

"""Builds the edge-cost function `app.routing.algorithm.shortest_path`
minimizes — the one place the two routing modes actually differ.

    risk_adjusted_cost = base_cost x (1 + risk_penalty x risk_score)

**Reuses `app.risk.formula.compute_risk_adjusted_cost` unmodified** for
the risk term — Milestone 6B's own formula, not a second, silently
different one. Accessibility is layered on top as a separate multiplier
(see `app.routing.accessibility`) — applied to *both* modes, since
accessibility is not part of "risk" at all; the only thing that
distinguishes `distance_only` from `risk_aware` is whether the risk term
is included.
"""

from collections.abc import Callable

from app.risk.config import RoadRiskConfig
from app.risk.formula import compute_risk_adjusted_cost
from app.roads.schemas import RoadEdge
from app.routing.accessibility import Traversability, resolve_accessibility
from app.routing.config import RoutingConfig
from app.routing.schemas import RoutingMode

EdgeCostFn = Callable[[RoadEdge], float | None]
"""`None` means the edge is not traversable (`blocked`) — excluded from
the search entirely, never assigned an infinite-but-finite cost."""


def build_edge_cost_fn(
    mode: RoutingMode, routing_config: RoutingConfig, risk_config: RoadRiskConfig
) -> EdgeCostFn:
    def cost(edge: RoadEdge) -> float | None:
        traversability = resolve_accessibility(
            edge.accessibility, routing_config.unknown_accessibility_policy
        )
        if traversability is Traversability.BLOCKED:
            return None

        effective_cost = edge.base_cost
        if mode is RoutingMode.RISK_AWARE:
            effective_cost = compute_risk_adjusted_cost(
                edge.base_cost, edge.risk_score, risk_config
            )

        if traversability is Traversability.RESTRICTED:
            effective_cost *= 1 + routing_config.restricted_accessibility_penalty

        return effective_cost

    return cost

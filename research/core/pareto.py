"""Distance-risk Pareto-efficiency analysis.

**This module never assumes the lowest-risk route is "best."** A route
minimizing risk alone, and a route minimizing distance alone, can both be
Pareto-efficient — neither dominates the other, because each is better on
one objective and worse on the other. `pareto_frontier()` returns every
non-dominated point; `describe_tradeoff()` reports the actual, computed
difference between the frontier's risk-minimizing and distance-minimizing
extremes, so a caller can state the trade-off in real numbers rather than
asserting one route is simply "optimal."
"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParetoPoint:
    label: str
    distance_km: float
    route_risk: float


def dominates(candidate: ParetoPoint, other: ParetoPoint) -> bool:
    """`True` if `candidate` dominates `other`: at least as good as
    `other` on both distance and risk, and strictly better on at least
    one."""
    at_least_as_good = (
        candidate.distance_km <= other.distance_km and candidate.route_risk <= other.route_risk
    )
    strictly_better = (
        candidate.distance_km < other.distance_km or candidate.route_risk < other.route_risk
    )
    return at_least_as_good and strictly_better


def pareto_frontier(points: Sequence[ParetoPoint]) -> list[ParetoPoint]:
    """The distance-risk Pareto-efficient subset of `points` (minimizing
    both objectives) — every point no other point dominates."""
    return [
        point
        for point in points
        if not any(dominates(other, point) for other in points if other is not point)
    ]


@dataclass(frozen=True, slots=True)
class TradeoffSummary:
    """A computed, never-asserted statement of the distance/risk
    trade-off between the lowest-risk and shortest-distance points among
    a set of routes. Both percentage fields can be `None` — see
    `research.core.metrics` for when."""

    lowest_risk: ParetoPoint
    shortest_distance: ParetoPoint
    lowest_risk_distance_overhead_percent: float | None
    shortest_distance_risk_excess_percent: float | None


def describe_tradeoff(points: Sequence[ParetoPoint]) -> TradeoffSummary:
    """Compares the lowest-risk point against the shortest-distance point
    among `points` (which may be the same point, if one route is best on
    both objectives). Requires at least one point."""
    if not points:
        raise ValueError("describe_tradeoff requires at least one point.")

    lowest_risk = min(points, key=lambda point: point.route_risk)
    shortest_distance = min(points, key=lambda point: point.distance_km)

    distance_overhead = None
    if shortest_distance.distance_km > 0:
        distance_overhead = (
            (lowest_risk.distance_km - shortest_distance.distance_km)
            / shortest_distance.distance_km
            * 100.0
        )

    risk_excess = None
    if lowest_risk.route_risk > 0:
        risk_excess = (
            (shortest_distance.route_risk - lowest_risk.route_risk) / lowest_risk.route_risk * 100.0
        )

    return TradeoffSummary(
        lowest_risk=lowest_risk,
        shortest_distance=shortest_distance,
        lowest_risk_distance_overhead_percent=distance_overhead,
        shortest_distance_risk_excess_percent=risk_excess,
    )

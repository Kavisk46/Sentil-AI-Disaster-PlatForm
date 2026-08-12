"""Shortest-path search over a road graph.

**Algorithm: Dijkstra's algorithm, via a binary heap (`heapq`).** See
apps/api/README.md ("Routing algorithm") for the full evaluation against
A* and why Dijkstra is what's actually wired in. In short: both edge-cost
formulas this milestone uses (`base_cost`, and the risk-adjusted cost from
`app.risk.formula.compute_risk_adjusted_cost`) are always non-negative, so
Dijkstra is directly applicable and provably optimal — the simplest
algorithm appropriate for that property, with no heuristic-admissibility
assumption that could silently break if a future cost formula changes.

This same implementation *is* A* when given a heuristic: Dijkstra is
exactly A* with a heuristic that always returns zero. `shortest_path()`
accepts an optional `heuristic` parameter for exactly this reason — this
is how "the architecture allows the routing algorithm to be replaced
later" without a second implementation. When a heuristic is supplied, it
must be **admissible** (never overestimate the true remaining cost) for
the result to stay optimal; `haversine_heuristic()` below (straight-line
distance to the destination) is admissible for both cost formulas this
milestone uses, since a real road distance is never shorter than the
straight-line distance between the same two points, and the risk-adjusted
cost is never less than the base distance cost (every multiplier is
`>= 1`). **This does not mean A* is always superior** — for the small,
prototype-scale graphs this milestone targets, Dijkstra's extra node
expansions are negligible, and Dijkstra's correctness doesn't depend on
an admissibility proof remaining valid as the cost formula evolves; A* is
an available, tested optimization (`RoutingConfig.use_astar_heuristic`),
not a default.
"""

import heapq
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.roads.geo_utils import haversine_distance_meters
from app.roads.schemas import RoadEdge, RoadNode
from app.routing.cost import EdgeCostFn

Heuristic = Callable[[RoadNode], float]
"""An admissible (never-overestimating) lower-bound estimate of the
remaining cost from a node to the destination."""


class PathfindingGraph(Protocol):
    """The minimal read surface `shortest_path()` needs — deliberately
    not `RoadNetworkRepository` itself (no `add_node`/`add_edge`, and no
    `app.services` import in `app.routing`, matching `app.roads`/
    `app.risk`'s own layering). `GraphView` below implements this
    structurally; so does `InMemoryRoadNetworkRepository`.
    """

    def get_node(self, node_id: str) -> RoadNode | None: ...
    def neighbors(self, node_id: str) -> list[RoadNode]: ...
    def get_edge(self, source_node: str, target_node: str) -> RoadEdge | None: ...


class GraphView:
    """A lightweight, in-memory, per-request adapter over `(nodes, edges)`
    presenting the same `PathfindingGraph` surface — **not a second,
    persistent road graph**. `edges` may be the road network's own edges
    (`distance_only`) or a risk-assessed copy from
    `app.risk.analyzer.compute_road_risk` (`risk_aware`, never written
    back into `RoadNetworkRepository` — see `app.risk`); either way, every
    node/edge here traces back 1:1 to the one canonical graph
    `RoadNetworkRepository` stores. Built fresh per routing request —
    O(nodes + edges), cheap at prototype scale (see apps/api/README.md,
    "Performance").
    """

    def __init__(self, nodes: list[RoadNode], edges: list[RoadEdge]) -> None:
        self._nodes = {node.node_id: node for node in nodes}
        self._edges = {(edge.source_node, edge.target_node): edge for edge in edges}
        self._adjacency: dict[str, list[str]] = {}
        for source_node, target_node in self._edges:
            self._adjacency.setdefault(source_node, []).append(target_node)

    def get_node(self, node_id: str) -> RoadNode | None:
        return self._nodes.get(node_id)

    def neighbors(self, node_id: str) -> list[RoadNode]:
        return [
            self._nodes[target_id]
            for target_id in self._adjacency.get(node_id, [])
            if target_id in self._nodes
        ]

    def get_edge(self, source_node: str, target_node: str) -> RoadEdge | None:
        return self._edges.get((source_node, target_node))


@dataclass(frozen=True, slots=True)
class PathResult:
    """The raw output of `shortest_path()` — before `app.routing.result_builder`
    turns it into the richer, API-facing `RouteResult`."""

    found: bool
    node_sequence: list[str] = field(default_factory=list)
    edge_sequence: list[RoadEdge] = field(default_factory=list)
    total_cost: float = 0.0


def haversine_heuristic(destination: RoadNode) -> Heuristic:
    """A valid, admissible A* heuristic: straight-line (great-circle)
    distance to `destination`. See the module docstring for the
    admissibility argument."""

    def heuristic(node: RoadNode) -> float:
        return haversine_distance_meters(
            node.latitude, node.longitude, destination.latitude, destination.longitude
        )

    return heuristic


def shortest_path(
    graph: PathfindingGraph,
    start_node_id: str,
    destination_node_id: str,
    edge_cost: EdgeCostFn,
    heuristic: Heuristic | None = None,
) -> PathResult:
    """Dijkstra (`heuristic=None`) or A* (`heuristic` given) over `graph`,
    minimizing the sum of `edge_cost(edge)` — edges where `edge_cost`
    returns `None` are treated as not traversable and never expanded.

    Uses the standard "lazy deletion" priority-queue pattern (`heapq` has
    no decrease-key): a node may be pushed more than once with different
    tentative costs; stale entries are skipped via the `visited` check
    after popping, not removed from the heap directly.
    """
    if graph.get_node(start_node_id) is None or graph.get_node(destination_node_id) is None:
        return PathResult(found=False)

    if start_node_id == destination_node_id:
        return PathResult(
            found=True, node_sequence=[start_node_id], edge_sequence=[], total_cost=0.0
        )

    estimate = heuristic or (lambda _node: 0.0)
    start_node = graph.get_node(start_node_id)
    assert start_node is not None  # already checked above; narrows the type for mypy

    best_cost: dict[str, float] = {start_node_id: 0.0}
    came_from_edge: dict[str, RoadEdge] = {}
    came_from_node: dict[str, str] = {}
    visited: set[str] = set()
    frontier: list[tuple[float, str]] = [(estimate(start_node), start_node_id)]

    while frontier:
        _, current_id = heapq.heappop(frontier)
        if current_id in visited:
            continue
        if current_id == destination_node_id:
            break
        visited.add(current_id)

        for neighbor in graph.neighbors(current_id):
            edge = graph.get_edge(current_id, neighbor.node_id)
            if edge is None:
                continue
            cost = edge_cost(edge)
            if cost is None:
                continue  # not traversable (blocked)

            tentative_cost = best_cost[current_id] + cost
            if tentative_cost < best_cost.get(neighbor.node_id, math.inf):
                best_cost[neighbor.node_id] = tentative_cost
                came_from_edge[neighbor.node_id] = edge
                came_from_node[neighbor.node_id] = current_id
                heapq.heappush(frontier, (tentative_cost + estimate(neighbor), neighbor.node_id))

    if destination_node_id not in best_cost:
        return PathResult(found=False)

    node_sequence = [destination_node_id]
    edge_sequence: list[RoadEdge] = []
    current = destination_node_id
    while current != start_node_id:
        edge_sequence.append(came_from_edge[current])
        current = came_from_node[current]
        node_sequence.append(current)
    node_sequence.reverse()
    edge_sequence.reverse()

    return PathResult(
        found=True,
        node_sequence=node_sequence,
        edge_sequence=edge_sequence,
        total_cost=best_cost[destination_node_id],
    )

"""Risk-aware rescue routing (Milestone 6C).

    API route -> RoutingService -> app.routing (engine)
        -> RoadNetworkRepository -> RoadRiskService -> RouteResult

Operates on the **same** road graph Milestone 6A built and Milestone 6B
annotated with risk — **no second road graph is created anywhere in this
package**. `app.routing` computes routes over `RoadNode`/`RoadEdge`
(`app.roads.schemas`) exactly as they come from `RoadNetworkRepository`
(distance-only) or `RoadRiskService`/`app.risk.analyzer.compute_road_risk`
(risk-aware) — this package only ever reads that data, never mutates it,
and never invents a parallel graph structure.

Two routing modes, sharing everything except the edge-cost function:

- `distance_only` — minimizes `RoadEdge.base_cost`. The control condition:
  what a routing engine ignorant of any damage/risk would produce.
- `risk_aware` — minimizes a risk-adjusted cost, reusing
  `app.risk.formula.compute_risk_adjusted_cost` **unmodified** (Milestone
  6B's own formula: `base_cost * (1 + cost_penalty_scale * risk_score)`)
  layered with an accessibility penalty (`app.routing.accessibility`).

## Files

- `config.py` — `RoutingConfig`: every routing-specific tunable constant,
  sourced from `Settings`.
- `accessibility.py` — `Traversability`/`resolve_accessibility`: turns
  `AccessibilityStatus` into a routing decision (open/penalized/blocked).
  Kept a genuinely separate concept from risk (see "Accessibility," below).
- `cost.py` — `build_edge_cost_fn`: combines accessibility + (optionally)
  risk into one edge-cost function for the algorithm.
- `algorithm.py` — `shortest_path`: Dijkstra via a binary heap, optionally
  configured as A* with an admissible haversine heuristic. See
  apps/api/README.md ("Routing algorithm") for the full evaluation.
- `nearest_node.py` — `InMemoryNearestNodeLocator`: maps an arbitrary
  `(latitude, longitude)` to the nearest graph node, within a configured
  maximum snap distance — never fabricates a match.
- `result_builder.py` — assembles a `RouteResult` from a found path.
- `metrics.py` — derived, purely descriptive research metrics (detour
  ratio, risky-segment counts, avoided high-risk edges) — never influence
  route selection.
- `geojson.py` — `route_to_feature`: converts a `RouteResult` into a
  standard GeoJSON `Feature` (a `LineString`).
- `schemas.py` — `RoutingMode`, `RouteResult`, `AccessibilitySummary`,
  `RouteComparison`.

`app.services.routing_service.RoutingService` is the DI-facing service
that wires this package's pure functions to `RoadNetworkRepository` and
`RoadRiskService` — see that module for how "no route" and "unavailable"
are represented.

## Accessibility is not risk

`open` roads are always traversable; `blocked` roads are never
traversable (excluded from the search entirely, not merely penalized);
`restricted` roads are traversable with a configurable cost penalty;
`unknown` roads (the state OSM ingestion always leaves — see
`app.roads`) follow a configurable policy (default: treated as `open`,
since treating the *entire* graph as blocked-by-default would make
routing unusable against today's honest state, where nothing has
confirmed accessibility yet). **A `critical`-risk edge is never
automatically reclassified as blocked** — accessibility only ever changes
via whatever evidence set it in the first place, never by looking at
`risk_score`.

## Do not implement (this milestone)

LLM summaries, hazard prediction, tsunami prediction, flood forecasting,
a 3D frontend, live navigation, traffic prediction, or real-time vehicle
tracking. All later milestones.
"""

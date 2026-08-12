# Routing Architecture

The routing subsystem computes rescue and access routes that account for
real, detected disaster impact — as opposed to conventional navigation
systems, which assume the underlying road network is fully intact.

## Responsibilities

- Maintain a routable representation of the road network for an affected
  region.
- Incorporate detected hazards and infrastructure damage as constraints or
  weight adjustments on that network.
- Compute viable routes between requested points, favoring safety and
  accessibility over raw shortest-path distance.

## Intended Structure

The routing subsystem operates on a graph representation of the road
network, sourced from open geospatial road data and enriched with hazard
information produced by the [AI engine](ai-engine.md).

Planned components within the routing subsystem:

- **Network ingestion** — importing and maintaining a routable road graph for
  a given region.
- **Hazard overlay** — applying detected damage as edge removals or
  weight penalties on the road graph.
- **Route computation** — pathfinding over the hazard-adjusted graph between
  responder-specified points.
- **Confidence reporting** — surfacing the confidence of detected hazards
  along a computed route, rather than presenting a single route as
  unconditionally safe.

## Key Interactions with Other Subsystems

- Consumes hazard and infrastructure-impact data produced by the
  [AI engine](ai-engine.md) via the [backend](backend.md).
- Returns computed routes to the backend for persistence and exposure
  through the API.
- Routes are rendered as an overlay on the [frontend](frontend.md) map
  dashboard.

## Status

Routing implementation begins in **Phase 5** of [`PROJECT_ROADMAP.md`](../../PROJECT_ROADMAP.md), building on the damage detection output delivered in Phase 4. Confidence-aware routing is tracked as a research extension in [`docs/research/future-work.md`](../research/future-work.md).

**Network ingestion has an early foundation** (Milestone 6A, ahead of Phase
5 proper): a directed graph representation (`RoadNode`/`RoadEdge`),
buildable from real OpenStreetMap data via the Overpass API, with every
edge carrying a `base_cost` (today: exactly distance) and placeholder
`risk_score`/`accessibility` fields the future "hazard overlay" component
will populate. See [`apps/api/README.md`](../../apps/api/README.md#road-network-milestone-6a)
for the full design.

**Hazard overlay has a first, explicitly heuristic pass** (Milestone 6B):
`GET /api/v1/analysis/{id}/road-risk` correlates georeferenced damage
predictions with nearby road edges (proximity-weighted by damage severity
and detection confidence) into a `risk_score`/`risk_level` per edge, kept
strictly separate from `accessibility` (risk is never treated as
blockage). See
[`apps/api/README.md`](../../apps/api/README.md#road-risk-model-milestone-6b)
for the full baseline heuristic formula and its documented limitations.

**Route computation has a first version** (Milestone 6C):
`POST /api/v1/routing` computes a `distance_only` (shortest-distance
control condition) or `risk_aware` route via Dijkstra (optionally A*,
with an admissible geographic heuristic), reusing Milestone 6B's
risk-adjusted cost formula unmodified and respecting accessibility
(`open`/`restricted`/`blocked`/`unknown`) as a concept kept separate from
risk. A route comparison capability (`distance_only` vs `risk_aware` for
the same start/destination, with distance/risk differences and a detour
ratio) exists at the service level. **Still not implemented:** multi-stop
routing, alternate-route ranking, live navigation, traffic-aware
routing, and any LLM-generated route explanation. See
[`apps/api/README.md`](../../apps/api/README.md#risk-aware-rescue-routing-milestone-6c)
for the full algorithm choice, cost formulas, and research metrics.

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

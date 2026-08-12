"""Road-network foundation for future emergency rescue routing (Milestone 6A).

    OpenStreetMap -> Road Network -> Graph -> Risk-weighted Graph -> Rescue Routing

This milestone builds only the first two arrows: turning raw OpenStreetMap
data into a directed graph. **No shortest-path routing (Dijkstra, A*, or
otherwise) is implemented here** — see "Do not implement," below.

Three deliberately separate concerns, each its own module:

- `osm_source.py` — OSM data **acquisition**: fetches/parses raw
  OpenStreetMap road data (via the Overpass API) into `OSMRoadData`. Knows
  nothing about graphs.
- `builder.py` — **graph construction**: turns `OSMRoadData` into
  `RoadNode`/`RoadEdge` records and populates a `RoadNetworkRepository`.
  Knows nothing about HTTP or where the OSM data came from.
- `app.services.road_network_repository` — the **graph abstraction**
  (`RoadNetworkRepository` Protocol + `InMemoryRoadNetworkRepository`).
  Nothing outside this package (or `app.services.road_network_repository`)
  ever sees a raw graph-library object — every caller depends on
  `RoadNode`/`RoadEdge`/`RoadGraph`, this package's own typed models.
- **Routing** (shortest-path algorithms, risk-aware weighting, route
  optimization) is explicitly out of scope — a later milestone.

## Why a graph is the right representation

A road network is naturally a graph: a **node** is a location or
intersection (a point where routing decisions can be made), an **edge** is
a traversable road segment connecting two nodes, and a **weight** is the
cost of traversing that edge. This is the standard representation for
shortest-path/routing problems (Dijkstra, A*, and every real-world
navigation system use exactly this abstraction) — nothing about
disaster-response routing changes that; it only changes what the weight
*means*.

Directed edges are required, not optional: many real roads are one-way,
so "can I get from A to B" is not always the same question as "can I get
from B to A." A directed graph (each edge has an explicit `source_node` /
`target_node`) is the only representation that can express that correctly;
an undirected graph would silently allow illegal-direction routes.

## Where the weight comes from — today and later

Every edge has a `base_cost` (Milestone 6A: exactly `distance` — see
`weighting.py`). Nothing here applies damage risk yet. The intended future
formula, once SentinelAI's damage/hazard intelligence (Milestone 5's
geospatial layer, and later hazard prediction) exists to feed it:

    weight = distance + damage_risk + hazard_risk + blockage_penalty

This is why `RoadEdge` already carries `risk_score` (always `None` today —
OSM has no concept of disaster risk, so nothing fabricates one) and
`accessibility` (always `AccessibilityStatus.UNKNOWN` from OSM ingestion —
see "Accessibility," below): the fields exist so a future milestone can
*populate* them from real analysis, without changing this milestone's
schema again.

## Accessibility: OSM alone never determines disaster blockage

`AccessibilityStatus` (`open`/`restricted`/`blocked`/`unknown`) is a field
on every edge, but OSM ingestion (`builder.py`) always sets it to
`unknown` — OpenStreetMap is a static basemap with no knowledge of an
ongoing disaster. A future milestone derives real `blocked`/`restricted`
status from SentinelAI's own damage/hazard intelligence (Milestone 5's
`BuildingDamage`/`DamagePriority`, and later hazard prediction) and
overlays it onto the graph — not implemented here.

## Do not implement (this milestone)

Shortest-path routing, A*, Dijkstra, route optimization,
damage-to-road intersection, hazard prediction, tsunami prediction, LLM
summaries, a frontend map, or 3D visualization. All later milestones.
"""

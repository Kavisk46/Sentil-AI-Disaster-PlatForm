"""Damage -> Road Risk (Milestone 6B).

    Damage Geometry + Road Geometry -> Spatial Analysis -> Road Risk -> Risk-aware Road Graph

Connects Milestone 5's geospatial damage predictions (`app.ml.schemas.BuildingDamage`)
with Milestone 6A's OpenStreetMap road graph (`app.roads`/
`app.services.road_network_repository`) to compute a **baseline heuristic
risk score** per road edge. Deliberately its own package — not folded into
`app.ml` or `app.roads` — because it is the bridge that consumes both,
mirroring how `app.roads.schemas.RoadEdge` needed to import
`app.ml.schemas.DamageClass` (see `app/roads/schemas.py`) rather than the
reverse: `app.risk` is one layer further out, dependent on both, depended
on by neither.

**No route optimization, no shortest-path routing, is implemented here.**
This package only produces risk-annotated `RoadEdge`s — see "Do not
implement" in `apps/api/README.md` ("Road risk model").

## Core principle: four distinct things, not one

This package (and its documentation) always distinguishes:

1. **Damage severity** — `BuildingDamage.damage_class`, a property of one
   building, unrelated to any road.
2. **Proximity to damage** — a purely geometric fact (`distance_meters` on
   `RiskSource`): how close a road edge is to a damaged building.
3. **Road risk** — `RoadEdge.risk_score`/`risk_level`, a derived,
   probabilistic-flavored *estimate* combining (1) and (2) (and
   confidence) via the baseline heuristic formula (`formula.py`).
4. **Road blockage** — `RoadEdge.accessibility`, a *separate* field this
   milestone never sets from risk. A `critical`-risk edge is not
   automatically `blocked`; blockage requires stronger evidence (a future
   milestone's job — see `app.roads.schemas.AccessibilityStatus`).

A damaged building near a road does not automatically mean the road is
blocked. Conflating (1)-(4) into a single number would hide exactly the
distinction a responder needs to reason about risk versus certainty.

## Pipeline stages (this module's own architecture)

- `config.py` — `RoadRiskConfig`: every tunable constant the formula uses,
  sourced from `Settings` (`app/core/config.py`) — nothing below hardcodes
  a weight or threshold inline.
- `formula.py` — the pure math: severity weight, distance decay,
  per-building contribution, aggregation (with normalization/capping),
  risk-level classification, and the risk-adjusted edge cost.
- `spatial.py` — point-to-road-segment distance (a geodesic-appropriate
  local projection, never raw lat/lon degree deltas — see the module
  docstring) and the coarse bounding-box pre-filter (the seam a future
  PostGIS spatial index replaces).
- `analyzer.py` — orchestrates the "Spatial Relationship" pipeline (obtain
  geometry -> find nearby damage -> distance -> contribution -> aggregate
  -> produce risk) into `compute_road_risk()`.

`app.services.road_risk_service.RoadRiskService` is the DI-facing service
(`GET /api/v1/analysis/{analysis_id}/road-risk`) that wires this package's
pure functions to `AnalysisProcessingService`, `SpatialRepository`, and
`RoadNetworkRepository` — see that module for how "unavailable" is
represented when geospatial damage data or a road network don't exist yet.

## Do not implement (this milestone)

Dijkstra, A*, route optimization, live navigation, hazard prediction,
tsunami prediction, LLM summaries, frontend changes, or 3D visualization.
All later milestones.
"""

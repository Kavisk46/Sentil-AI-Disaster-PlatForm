# API Reference

This document describes SentinelAI's versioned REST API surface: the
endpoints the frontend and external integrations use to read and write
incidents, imagery, detections, routes, and briefings.

## Currently Implemented

### `GET /`

Root endpoint; identifies the project and its current version for whoever
(or whatever) hits the API base URL.

**Response `200`**

```json
{ "name": "SentinelAI API", "description": "...", "version": "0.1.0", "docs_url": "/docs" }
```

### `GET /health`

Unversioned liveness check, for orchestrators (Docker, load balancers) —
see [`docs/architecture/backend.md`](../architecture/backend.md) for why it
sits outside `/api/v1`.

**Response `200`**

```json
{ "status": "ok", "timestamp": "2026-01-01T00:00:00Z" }
```

### `GET /api/v1`

Confirms the v1 API surface itself is reachable, independent of any
specific resource under it.

**Response `200`**

```json
{ "version": "0.1.0", "status": "available" }
```

### `GET /api/v1/system/info`

Basic, non-sensitive service metadata. Exists to prove out API versioning
end-to-end; carries no business data.

**Response `200`**

```json
{ "name": "SentinelAI API", "version": "0.1.0", "environment": "development" }
```

### `GET /api/v1/model/status`

Whether the damage-classification model is enabled and actually loaded
(Milestone F4) — see [`apps/api/README.md`](../../apps/api/README.md#milestone-f4--real-inference)
for the full model-lifecycle design. Read-only; never triggers a load of
its own (it reports on whatever the existing DI wiring already
constructed/cached).

**Response `200`, real inference enabled and loaded**

```json
{
  "enabled": true,
  "provider": "open_clip",
  "status": {
    "model_loaded": true,
    "model_name": "deterministic-tile-localizer+ViT-B-32",
    "model_version": "openai",
    "device": "cpu"
  }
}
```

`enabled=false` means real inference was never attempted
(`Settings.MODEL_ENABLED=false`) — every analysis will end
`MODEL_UNAVAILABLE`, by configuration, not a fault. `enabled=true` with
`status.model_loaded=false` means a real load was attempted and hasn't
(yet) succeeded — check server logs. No error responses — always `200`.

### `POST /api/v1/analysis`

Upload an aerial/satellite image, store it, and dispatch it for analysis.
Returns immediately with status `queued` — it does not wait for inference
to finish. See "Analysis lifecycle" in
[`apps/api/README.md`](../../apps/api/README.md#analysis-lifecycle-milestone-4)
for the full status model. As of Milestone F4, the default configuration
performs real CPU-only model inference and a real image reaches
`completed` — see
[`apps/api/README.md`](../../apps/api/README.md#milestone-f4--real-inference).
Setting `MODEL_ENABLED=false` restores the original honest
`MODEL_UNAVAILABLE`-always behavior for an offline/no-network deployment.

**Request** — `multipart/form-data`, field name `image`. Supported types:
JPEG, PNG, WEBP (validated by decoding the actual bytes, not the declared
`Content-Type`). Maximum size is configurable
(`MAX_UPLOAD_SIZE_MB`, default 10 MB).

**Response `201`**

```json
{ "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10", "status": "queued", "filename": "aerial.jpg" }
```

`status` is one of `uploaded` / `queued` / `processing` / `completed` /
`failed` (`app/schemas/analysis.py`); the response always reports `queued`
since dispatch happens synchronously before this response is returned.

**Errors:** `400` (undecodable image content), `413` (too large), `415`
(unsupported type), `422` (missing `image` field). See
[`apps/api/README.md`](../../apps/api/README.md#post-apiv1analysis--upload--dispatch)
for full details and security considerations.

### `GET /api/v1/analysis/{analysis_id}`

Read an analysis's current lifecycle status and, once available, its
result (`DamageAnalysis`, `app/ml/schemas.py`) or structured failure. Safe
to poll — never triggers or re-triggers processing.

**Response `200`, completed (Milestone F4's real default)**

```json
{
  "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10",
  "status": "completed",
  "summary": { "total_buildings": 4, "damaged_buildings": 2, "severely_damaged": 1, "destroyed": 0 },
  "buildings": [
    {
      "building_id": "building_0",
      "damage_class": "minor",
      "confidence": 0.41,
      "bounding_box": { "x_min": 0, "y_min": 0, "x_max": 256, "y_max": 256 },
      "geometry": { "type": "polygon", "coordinates": [["..."]] },
      "coordinate_reference_system": "IMAGE",
      "georeferenced": false
    }
  ],
  "model_metadata": {
    "model_loaded": true,
    "model_name": "deterministic-tile-localizer+ViT-B-32",
    "model_version": "openai",
    "device": "cpu"
  },
  "failure": null,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:01Z"
}
```

`confidence` is CLIP's own raw softmax output — genuine model output,
**not a calibrated probability** (see
[`apps/api/README.md`](../../apps/api/README.md#confidence-interpretation-f4--read-before-using-confidence)).
`coordinate_reference_system: "IMAGE"`/`georeferenced: false` — pixel
coordinates, never geographic ones (see "CRS safety" throughout this
document and `docs/architecture/intelligence.md`).

**Response `200`, failed** — unchanged shape, `buildings: []`,
`summary`/`model_metadata: null`, and a structured `failure` (`code`
one of `MODEL_UNAVAILABLE`/`MODEL_LOAD_FAILURE`/`INVALID_IMAGE`/
`PREPROCESSING_FAILURE`/`POSTPROCESSING_FAILURE`/`INFERENCE_FAILURE` —
see `apps/api/README.md`, "Model unavailable / inference failure").

**Errors:** `404` (no analysis with that id), `422` (`analysis_id` isn't a
valid UUID). See
[`apps/api/README.md`](../../apps/api/README.md#get-apiv1analysisanalysis_id--read-statusresult)
for the full status model, architecture, and a POST-then-GET example.

### `GET /api/v1/analysis/{analysis_id}/damage-map`

Read the same analysis's building predictions as standard GeoJSON
(RFC 7946) — see "Geospatial damage intelligence" in
[`apps/api/README.md`](../../apps/api/README.md#geospatial-damage-intelligence-milestone-5)
for the full design, including why pixel coordinates are never reinterpreted
as GPS coordinates. Always `200` for a known `analysis_id`; `available`
tells you whether `feature_collection` actually has anything to plot.

**Response `200`**

```json
{
  "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10",
  "status": "completed",
  "available": true,
  "reason": null,
  "feature_collection": {
    "type": "FeatureCollection",
    "coordinate_reference_system": "IMAGE",
    "features": [
      {
        "type": "Feature",
        "geometry": { "type": "Polygon", "coordinates": [[[10, 20], [110, 20], [110, 120], [10, 120], [10, 20]]] },
        "properties": {
          "building_id": "building_0",
          "damage_class": "destroyed",
          "confidence": 0.95,
          "priority": "critical",
          "georeferenced": false
        }
      }
    ]
  }
}
```

`"coordinate_reference_system": "IMAGE"` / `"georeferenced": false` means
these coordinates are pixel positions in the source image, **not**
longitude/latitude — check this before plotting on a geographic map.

**Errors:** `404` (no analysis with that id), `422` (`analysis_id` isn't a
valid UUID).

### `GET /api/v1/roads/status`

Whether a road network is currently loaded in memory, and its size/bounds
if so — see "Road network" in
[`apps/api/README.md`](../../apps/api/README.md#road-network-milestone-6a)
for the full graph architecture. This is deliberately the *only*
road-network endpoint this milestone exposes — no ingestion trigger, no
raw graph dump, no routing. Nothing loads OSM data automatically, so a
fresh deployment always reports unavailable.

**Response `200`**

```json
{
  "loaded": false,
  "node_count": 0,
  "edge_count": 0,
  "bounds": null,
  "message": "Road network unavailable: no road data has been loaded for any region yet."
}
```

No error responses — always `200`.

### `GET /api/v1/analysis/{analysis_id}/road-risk`

Correlates the analysis's georeferenced damage predictions with the
loaded road network, returning every road edge annotated with
`risk_score`/`risk_level`/`risk_sources` (plus `accessibility`, always
independent of risk) — see "Road risk model" in
[`apps/api/README.md`](../../apps/api/README.md#road-risk-model-milestone-6b)
for the full baseline heuristic formula, distance method, and why risk is
never conflated with blockage. Always `200`; `available` tells you
whether `edges` actually has an assessment. `POST /api/v1/routing`
(below) is what actually consumes this to compute a route.

**Response `200`, unavailable**

```json
{
  "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10",
  "status": "failed",
  "available": false,
  "reason": "Analysis is not completed yet (status=failed).",
  "edges": []
}
```

**Errors:** `404` (no analysis with that id), `422` (`analysis_id` isn't a
valid UUID).

### `POST /api/v1/routing`

Computes a `distance_only` (shortest-distance control condition) or
`risk_aware` route between two WGS84 coordinates, over the same road
graph the endpoints above expose — see "Risk-aware rescue routing" in
[`apps/api/README.md`](../../apps/api/README.md#risk-aware-rescue-routing-milestone-6c)
for the full algorithm (Dijkstra, optionally A*), cost formulas
(`risk_aware` reuses Milestone 6B's `compute_risk_adjusted_cost`
unmodified), and accessibility rules (`blocked` excluded entirely;
`restricted` penalized; risk is never conflated with blockage).
Coordinates are snapped to the nearest graph node, never assumed to
exactly match one. Always `200`; `found` tells you whether a route
actually exists — a `found=false` response is a structured result, not
an empty one, with `reason` explaining why.

**Request**

```json
{
  "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10",
  "start": { "latitude": 10.0, "longitude": 20.0 },
  "destination": { "latitude": 9.99, "longitude": 20.002 },
  "mode": "risk_aware"
}
```

**Response `200`, found**

```json
{
  "routing_mode": "risk_aware",
  "found": true,
  "start_node": "A",
  "destination_node": "F",
  "node_sequence": ["A", "D", "E", "F"],
  "edge_sequence": ["... RoadEdge objects, each with base_cost/risk_score/risk_level/accessibility ..."],
  "route_geometry": [[20.0, 10.0], [20.0, 9.99], [20.001, 9.99], [20.002, 9.99]],
  "total_distance": 300.0,
  "total_cost": 300.0,
  "accumulated_risk": 0.0,
  "number_of_edges": 3,
  "accessibility_summary": { "open": 0, "restricted": 0, "blocked": 0, "unknown": 3 },
  "reason": null
}
```

**Errors:** `404` (no analysis with that id), `422` (invalid
`start`/`destination` coordinates, or a missing/invalid `mode`).

### `GET /api/v1/analysis/{analysis_id}/intelligence`

The **analysis-aware** Disaster Intelligence Core entry point (Milestone
F3) — adapts this analysis's real damage/road-risk output into F2's
domain model (`app/intelligence/analysis_adapter.py`) and reports
whether enough evidence exists to build intelligence from it at all. See
[`docs/architecture/intelligence.md`](../architecture/intelligence.md),
"Milestone F3," for the full adapter design, the `analysis_id`/
`disaster_id` relationship, and why they are deliberately not the same
identifier. Distinct from `GET /api/v1/intelligence/{disaster_id}`
(F2, below): that path always serves the deterministic demo scenario;
this path serves real analysis-derived data, keyed by the existing
`analysis_id`.

**Response `200`, available**

```json
{
  "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10",
  "disaster_id": "7c2e4b1a-...",
  "context_available": true,
  "context_unavailable_reason": null,
  "is_simulated": false,
  "affected_area_count": 3,
  "hazard_count": 0,
  "infrastructure_count": 5,
  "roads_available": true,
  "roads_unavailable_reason": null,
  "resources_available": true,
  "resources_are_demo": true
}
```

**Response `200`, unavailable**

```json
{
  "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10",
  "disaster_id": "7c2e4b1a-...",
  "context_available": false,
  "context_unavailable_reason": "NO_GEOREFERENCE",
  "is_simulated": false,
  "affected_area_count": 0,
  "hazard_count": 0,
  "infrastructure_count": 0,
  "roads_available": false,
  "roads_unavailable_reason": "No road network is loaded.",
  "resources_available": true,
  "resources_are_demo": true
}
```

`context_unavailable_reason` is one of `ANALYSIS_NOT_COMPLETED`,
`MODEL_UNAVAILABLE`, `INFERENCE_FAILURE`, `NO_GEOREFERENCE`,
`INSUFFICIENT_EVIDENCE` — never fabricated when evidence is missing.
`resources_are_demo` is `true` unconditionally: no real
resource-ingestion system exists, so matched resources must never be
mistaken for live telemetry even when the surrounding analysis is real.

**Errors:** `404` (no analysis with that id), `422` (`analysis_id` isn't
a valid UUID).

### `GET /api/v1/analysis/{analysis_id}/intelligence/search-zones`

The same analysis's damage evidence, scored into ranked `SearchZone`s by
F2's unmodified `search_priority.py` engine — same shape and same
"never a location claim" discipline as F2's disaster-scoped
`.../search-zones` endpoint below, just sourced from real damage
observations instead of the demo scenario. `search_zones` is `[]`
(not an error) whenever `context_available` is `false`.

**Errors:** `404` (no analysis with that id), `422` (`analysis_id` isn't
a valid UUID).

### `GET /api/v1/analysis/{analysis_id}/intelligence/recommendations`

Ranked `Recommendation`s (F2's unmodified `recommendation.py` engine)
**plus** resource-capability-match detail for the single top-priority
search zone — bundled into one response rather than a fourth/fifth
endpoint, since "what can reach the top zone" is always read alongside
"what should we do." Each `resource_candidates` entry carries the F2
`CapabilityMatchResult` (can-perform/is-available/can-reach/route-
operational, kept as four separate signals) plus a `route_feasibility`
block:

```json
{
  "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10",
  "disaster_id": "7c2e4b1a-...",
  "context_available": true,
  "context_unavailable_reason": null,
  "recommendations": [ "... Recommendation objects, each with rationale/supporting_evidence/uncertainty/limitations ..." ],
  "top_search_zone_id": "9f0a...",
  "resource_candidates": [
    {
      "match": { "resource_id": "...", "eligible": true, "reachability": "reachable", "...": "..." },
      "route": { "found": true, "total_distance": 210.0, "...": "..." },
      "route_feasibility": { "status": "computed", "reason": null }
    }
  ],
  "resources_are_demo": true,
  "roads_available": true,
  "roads_unavailable_reason": null
}
```

`route_feasibility.status` is one of:

- `"computed"` — a real route was actually attempted via the same
  `RoutingService` engine `POST /api/v1/routing` uses (which may itself
  report `found=false`) — never invented geometry.
- `"route_unavailable"` — no road network is loaded, or a location isn't
  tagged `EPSG:4326`; a candidate is never routed as if untagged/pixel
  coordinates were geographic.
- `"not_applicable"` — the candidate failed an earlier capability/
  availability/reachability gate, or route feasibility is only computed
  for the single top-ranked candidate (never every candidate, to keep
  this bounded).

**Errors:** `404` (no analysis with that id), `422` (`analysis_id` isn't
a valid UUID).

### `GET /api/v1/intelligence/{disaster_id}`

The **Disaster Intelligence Core** (Milestone F2) — a deterministic
domain model and decision layer distinct from the analysis lifecycle
above (a `disaster_id` is not an `analysis_id`; see
[`docs/architecture/intelligence.md`](../architecture/intelligence.md)).
Returns the `Disaster` record and a count of every recorded intelligence
entity. As of F2 the only disaster this API can return is the
deterministic, `is_simulated=true` demo scenario
(`app/intelligence/demo_scenario.py`) — there is no ingestion endpoint
yet for a real disaster.

**Response `200`**

```json
{
  "disaster": {
    "id": "...", "type": "flood", "label": "DEMO: Coastal Flooding Scenario",
    "status": "active", "is_simulated": true, "source": "demo_scenario", "...": "..."
  },
  "observation_count": 4, "affected_area_count": 3, "hazard_count": 2,
  "resource_count": 5, "infrastructure_count": 3, "route_count": 1
}
```

**Errors:** `404` (no disaster with that id), `422` (`disaster_id` isn't
a valid UUID).

### `GET /api/v1/intelligence/{disaster_id}/search-zones`

Ranked `SearchZone`s, scored from the disaster's recorded `AffectedArea`s
by the deterministic search-priority scorer
(`app/intelligence/search_priority.py`) — never a claim that a person is
located there, always "high-priority search zone based on available
evidence." Every zone discloses which factors were actually scoreable
(`factors`) and which were not (`missing_factors`), plus `reasons` and
an `uncertainty` object (`confidence` always `null` — this is a
heuristic score, not a calibrated probability).

**Errors:** `404` (no disaster with that id).

### `GET /api/v1/intelligence/{disaster_id}/resources`

The disaster's recorded `Resource` registry, unranked (ranking is
target-specific — see `app/intelligence/capability_matching.py`, used
internally by the recommendations endpoint below).

**Errors:** `404` (no disaster with that id).

### `GET /api/v1/intelligence/{disaster_id}/recommendations`

Ranked, rule-based `Recommendation`s from the deterministic
recommendation engine (`app/intelligence/recommendation.py`) — computed
fresh on every call from the disaster's search zones, hazards,
infrastructure, and resources, never cached. Every recommendation
carries a `rationale`, `supporting_evidence`, and `uncertainty` — never
an unexplained action. No LLM is used for this endpoint.

**Errors:** `404` (no disaster with that id).

Interactive OpenAPI docs are available at `/docs` (Swagger UI) and `/redoc`
whenever the API is running.

## Planned Structure

Further domain endpoints are added starting in **Phase 2 — Backend** of
[`PROJECT_ROADMAP.md`](../../PROJECT_ROADMAP.md), grouped by resource
following the domain model described in
[`docs/architecture/backend.md`](../architecture/backend.md):

- **Incidents** — creating and querying disaster incidents.
- **Detections** — querying AI-detected damage and infrastructure impact records, once AI processing (Phase 4) exists.
- **Routes** — requesting and retrieving computed rescue/access routes.
  A first, single-origin/single-destination version exists today
  (`POST /api/v1/routing`, above); multi-stop routing, alternate-route
  ranking, and persistence/retrieval of past routes remain planned.
- **Briefings** — retrieving generated operational briefings for an incident.

For each, this document will describe the HTTP method and path, request/response
schemas, authentication requirements, and example requests.

## Versioning

The API is versioned via a URL path prefix (`/api/v1/...`, see
`app/core/constants.py`) so breaking changes can be introduced in a new
version without disrupting existing integrations.

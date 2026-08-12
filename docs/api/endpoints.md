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

### `POST /api/v1/analysis`

Upload an aerial/satellite image, store it, and dispatch it for analysis.
Returns immediately with status `queued` — it does not wait for inference
to finish. See "Analysis lifecycle" in
[`apps/api/README.md`](../../apps/api/README.md#analysis-lifecycle-milestone-4)
for the full status model and why every analysis currently ends up
`failed` (no trained model exists yet).

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

**Response `200`**

```json
{
  "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10",
  "status": "failed",
  "summary": null,
  "buildings": [],
  "model_metadata": null,
  "failure": { "code": "MODEL_UNAVAILABLE", "message": "..." },
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:01Z"
}
```

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

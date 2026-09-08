# SentinelAI Backend

FastAPI backend service. Milestone 2 added the platform's first real
capability — image ingestion — on top of the Milestone 1 foundation
(configuration, logging, middleware, API versioning, health/root checks).
Milestone 3A added the *architecture* for damage-intelligence inference.
Milestone 3B added the dataset pipeline a future training run will
consume. Milestone 3C adds the first concrete, CPU-compatible model
adapters — a real (if not yet trained) two-stage building-localization +
damage-classification pipeline. Milestone 4 connects upload, the analysis
lifecycle, and ML inference end-to-end: `POST /api/v1/analysis` now
dispatches every upload for processing and `GET /api/v1/analysis/{id}`
reads back its current status/result. Milestone 5 adds a geospatial layer
on top of a completed result: `GET /api/v1/analysis/{id}/damage-map`
converts building predictions into standard GeoJSON, ready for
Leaflet/Mapbox/MapLibre — **without ever inventing a latitude/longitude**
(see "Geospatial damage intelligence," below). Milestone 6A adds the
road-network foundation future rescue routing will need: a directed graph
of `RoadNode`/`RoadEdge`s, buildable from real OpenStreetMap data via the
Overpass API, with `GET /api/v1/roads/status` as the only exposed
endpoint — see "Road network," below. Milestone 6B connects the two:
`GET /api/v1/analysis/{id}/road-risk` correlates a completed analysis's
georeferenced damage predictions with nearby road edges using a
**baseline heuristic risk model** (explicitly labeled as such — not
scientifically validated), producing a `risk_score`/`risk_level` per edge
without ever conflating risk with blockage — see "Road risk model,"
below. Milestone 6C closes the loop with an actual routing engine:
`POST /api/v1/routing` computes a `distance_only` (control condition) or
`risk_aware` route over that same road graph via Dijkstra (optionally
A*), respecting accessibility (`open`/`restricted`/`blocked`) as a
concept **kept separate from risk** — see "Risk-aware rescue routing,"
below. **No shortest-path routing existed before this milestone, and
route optimization/live navigation still don't** — see that section's
own "Do not implement." **No model has been trained**, so every analysis
today still ends up `failed` with `MODEL_UNAVAILABLE` — see "Analysis
lifecycle," below. Milestone F2 adds the **Disaster Intelligence
Core**: a typed domain model (`Disaster`/`Observation`/`AffectedArea`/
`SearchZone`/`Hazard`/`Resource`/`RescueTeam`/`Infrastructure`/`Route`/
`HazardPrediction`/`Recommendation`/`Evidence`/`Uncertainty`) plus a
**deterministic, rule-based** search-priority scorer, capability
matcher, and recommendation engine — no ML model, no LLM. See
[`docs/architecture/intelligence.md`](../../docs/architecture/intelligence.md)
for the full pipeline and "Disaster Intelligence Core," below, for the
endpoints. Milestone F3 connects that Core to real analysis output —
`GET /api/v1/analysis/{analysis_id}/intelligence[...]` adapts a
completed analysis's own damage/road-risk results into the same domain
model and reuses F2's engines unmodified, with real route-feasibility
computed via the existing routing engine — see "Analysis-Aware
Intelligence (Milestone F3)," below. Still no database or authentication.

See [`docs/architecture/backend.md`](../../docs/architecture/backend.md)
for the architecture and layering conventions, and
[`docs/api/endpoints.md`](../../docs/api/endpoints.md) for the full API
reference.

## Local development

```bash
python -m venv .venv
.venv/Scripts/activate       # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs (Swagger UI) and `/redoc`

## Endpoints

| Method & Path | Purpose |
|---|---|
| `GET /` | Project identification and current API version |
| `GET /health` | Liveness check |
| `GET /api/v1` | Confirms the v1 API surface is available |
| `GET /api/v1/system/info` | Basic, non-sensitive service metadata |
| `POST /api/v1/analysis` | Upload an image and dispatch it for analysis (see below) |
| `GET /api/v1/analysis/{analysis_id}` | Read an analysis's current status/result (see below) |
| `GET /api/v1/analysis/{analysis_id}/damage-map` | Read an analysis's spatial (GeoJSON) representation (see below) |
| `GET /api/v1/roads/status` | Whether a road network is loaded, and its size/bounds (see below) |
| `GET /api/v1/analysis/{analysis_id}/road-risk` | Read the risk-aware road representation for an analysis (see below) |
| `POST /api/v1/routing` | Compute a `distance_only` or `risk_aware` route (see below) |
| `GET /api/v1/intelligence/{disaster_id}` | Disaster Intelligence Core: disaster record + entity counts (see below) |
| `GET /api/v1/intelligence/{disaster_id}/search-zones` | Ranked search zones, scored from recorded affected areas (see below) |
| `GET /api/v1/intelligence/{disaster_id}/resources` | The recorded resource registry for a disaster (see below) |
| `GET /api/v1/intelligence/{disaster_id}/recommendations` | Ranked, rule-based response recommendations (see below) |

### `POST /api/v1/analysis` — upload + dispatch

Accepts an aerial/satellite image, stores it, creates an analysis record,
and dispatches it for processing. Returns immediately — it does not wait
for inference to finish (see "Analysis lifecycle," below).

**Request** — `multipart/form-data`, field name `image`:

```bash
curl -X POST http://localhost:8000/api/v1/analysis \
  -F "image=@aerial.jpg;type=image/jpeg"
```

**Supported types:** JPEG, PNG, WEBP — determined by actually decoding the
file with Pillow, not by trusting the client's declared `Content-Type` or
filename extension (see Security, below).

**Maximum size:** configurable via `MAX_UPLOAD_SIZE_MB` (default `10`; see
`.env.example`).

**Response** — `201 Created`:

```json
{
  "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10",
  "status": "queued",
  "filename": "aerial.jpg"
}
```

`status` is `"queued"` by the time this response is returned — Milestone 4
dispatches the analysis for background processing before responding (see
"Analysis lifecycle," below). This response's shape is otherwise
unchanged from Milestone 2.

**Error responses:**

| Status | Cause |
|---|---|
| `400 Bad Request` | File content isn't decodable as an image (corrupted, or not an image at all) |
| `413 Payload Too Large` | File exceeds `MAX_UPLOAD_SIZE_MB` |
| `415 Unsupported Media Type` | Declared or actual (Pillow-detected) type isn't JPEG/PNG/WEBP |
| `422 Unprocessable Entity` | `image` field missing from the request |

### `GET /api/v1/analysis/{analysis_id}` — read status/result

Returns the analysis's current lifecycle status and, once available, its
result or failure. Safe to poll repeatedly — it only ever reads persisted
state, never triggers or re-triggers processing.

```bash
curl http://localhost:8000/api/v1/analysis/5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10
```

**Response `200`** (see "Analysis lifecycle," below, for what each field
looks like at each status):

```json
{
  "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10",
  "status": "failed",
  "summary": null,
  "buildings": [],
  "model_metadata": null,
  "failure": {
    "code": "MODEL_UNAVAILABLE",
    "message": "Stage 1 (building localization) is unavailable: ..."
  },
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:01Z"
}
```

**Error responses:**

| Status | Cause |
|---|---|
| `404 Not Found` | No analysis exists with the given (well-formed) UUID |
| `422 Unprocessable Entity` | `analysis_id` path segment isn't a valid UUID |

### `GET /api/v1/analysis/{analysis_id}/damage-map` — spatial (GeoJSON) result

Returns the same completed analysis's building predictions as a standard
GeoJSON `FeatureCollection` (see "Geospatial damage intelligence," below,
for the full design). Always `200` for a known `analysis_id` — even when
there's nothing to map yet, the response says so explicitly rather than
guessing or fabricating anything.

```bash
curl http://localhost:8000/api/v1/analysis/5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10/damage-map
```

**Response `200`, not yet mappable** (analysis not `completed`, or
`completed` with no building geometry — the only case this codebase's
current, untrained model can actually reach):

```json
{
  "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10",
  "status": "failed",
  "available": false,
  "reason": "Analysis is not completed yet (status=failed).",
  "feature_collection": { "type": "FeatureCollection", "features": [], "coordinate_reference_system": "IMAGE" }
}
```

**Response `200`, mappable** (a `completed` analysis with at least one
building that has geometry):

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

Note `"coordinate_reference_system": "IMAGE"` and
`"properties.georeferenced": false` — this GeoJSON's coordinates are
**pixel coordinates of the uploaded image, not longitude/latitude**. See
"Image-space mode" under "Geospatial damage intelligence," below, before
plotting this on a geographic map.

**Error responses:**

| Status | Cause |
|---|---|
| `404 Not Found` | No analysis exists with the given (well-formed) UUID |
| `422 Unprocessable Entity` | `analysis_id` path segment isn't a valid UUID |

### `GET /api/v1/roads/status` — road-network diagnostic

Reports whether a road network is currently loaded in memory, and its
size/bounds if so. See "Road network," below, for the full design — this
is deliberately the *only* road-network endpoint this milestone exposes;
there is no ingestion-trigger or raw-graph-dump endpoint yet.

```bash
curl http://localhost:8000/api/v1/roads/status
```

**Response `200`, unavailable** (the default — nothing ingests OSM data
automatically, so this is what a fresh deployment always returns):

```json
{
  "loaded": false,
  "node_count": 0,
  "edge_count": 0,
  "bounds": null,
  "message": "Road network unavailable: no road data has been loaded for any region yet."
}
```

**Response `200`, loaded** (after a future ingestion command populates the
repository):

```json
{
  "loaded": true,
  "node_count": 1842,
  "edge_count": 3910,
  "bounds": { "type": "bounding_box", "coordinates": [-122.42, 37.77, -122.40, 37.79] },
  "message": null
}
```

### `GET /api/v1/analysis/{analysis_id}/road-risk` — risk-aware road representation

Correlates a completed analysis's georeferenced damage predictions with
the loaded road network, returning every road edge annotated with a
`risk_score`/`risk_level`/`risk_sources` (`accessibility` is always
reported too, but never changed by this — see "Accessibility is
independent of risk" under "Road risk model," below). Always `200`;
`available` tells you whether `edges` actually has an assessment.

```bash
curl http://localhost:8000/api/v1/analysis/5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10/road-risk
```

**Response `200`, unavailable** (any of: analysis not `completed`, no
georeferenced damage geometry, or no road network loaded — the first two
are the honest, expected state for every analysis today, since no real
georeferencing pipeline or OSM ingestion has run):

```json
{
  "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10",
  "status": "failed",
  "available": false,
  "reason": "Analysis is not completed yet (status=failed).",
  "edges": []
}
```

**Response `200`, available**:

```json
{
  "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10",
  "status": "completed",
  "available": true,
  "reason": null,
  "edges": [
    {
      "source_node": "1", "target_node": "2",
      "distance": 111.0, "base_cost": 111.0,
      "road_type": "residential", "one_way": false,
      "accessibility": "unknown",
      "risk_score": 0.82, "risk_level": "high",
      "risk_sources": [
        { "building_id": "building_0", "damage_class": "destroyed", "confidence": 0.9, "distance_meters": 22.1, "contribution": 0.82 }
      ]
    }
  ]
}
```

Note `"accessibility": "unknown"` alongside `"risk_level": "high"` in the
same edge — risk and accessibility are deliberately independent (see
"Road risk model," below). `POST /api/v1/routing` (below) is what
actually consumes `risk_score`/`base_cost` to compute a route.

**Errors:** `404` (no analysis with that id), `422` (`analysis_id` isn't a
valid UUID).

### `POST /api/v1/routing` — compute a route

Computes a `distance_only` (shortest-distance control condition) or
`risk_aware` route between two coordinates, over the same road graph
`GET /api/v1/roads/status`/`GET .../road-risk` already expose — see
"Risk-aware rescue routing," below, for the full algorithm, cost
formulas, and accessibility rules. Coordinates are snapped to the nearest
graph node (never assumed to exactly match one); always `200`, with
`found` telling you whether a route actually exists.

```bash
curl -X POST http://localhost:8000/api/v1/routing \
  -H "Content-Type: application/json" \
  -d '{
    "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10",
    "start": { "latitude": 10.0, "longitude": 20.0 },
    "destination": { "latitude": 9.99, "longitude": 20.002 },
    "mode": "risk_aware"
  }'
```

**Response `200`, found**

```json
{
  "routing_mode": "risk_aware",
  "found": true,
  "start_node": "A",
  "destination_node": "F",
  "node_sequence": ["A", "D", "E", "F"],
  "edge_sequence": [ { "source_node": "A", "target_node": "D", "distance": 100.0, "base_cost": 100.0, "risk_score": 0.0, "risk_level": "low", "accessibility": "unknown", "risk_sources": [] } ],
  "route_geometry": [[20.0, 10.0], [20.0, 9.99], [20.001, 9.99], [20.002, 9.99]],
  "total_distance": 300.0,
  "total_cost": 300.0,
  "accumulated_risk": 0.0,
  "number_of_edges": 3,
  "accessibility_summary": { "open": 0, "restricted": 0, "blocked": 0, "unknown": 3 },
  "reason": null
}
```

**Response `200`, not found** (any of: no road network loaded, no node
near the requested coordinates, no georeferenced damage data for
`risk_aware` specifically, or no path exists in the graph):

```json
{
  "routing_mode": "risk_aware",
  "found": false,
  "start_node": null,
  "destination_node": null,
  "node_sequence": [],
  "edge_sequence": [],
  "route_geometry": [],
  "total_distance": null,
  "total_cost": null,
  "accumulated_risk": null,
  "number_of_edges": 0,
  "accessibility_summary": { "open": 0, "restricted": 0, "blocked": 0, "unknown": 0 },
  "reason": "No road network is loaded (see GET /api/v1/roads/status)."
}
```

**Errors:** `404` (no analysis with that id), `422` (invalid
`start`/`destination` coordinates, or a missing/invalid `mode`).

### `GET /api/v1/intelligence/{disaster_id}[/search-zones|/resources|/recommendations]` — Disaster Intelligence Core

Four read-only endpoints over a **different identifier** than everything
above: `disaster_id`, not `analysis_id` — a `Disaster` (Milestone F2)
spans observations, hazards, resources, and infrastructure, not one
uploaded image. See "Disaster Intelligence Core (Milestone F2)," below,
and [`docs/architecture/intelligence.md`](../../docs/architecture/intelligence.md)
for the full domain model and algorithms.

```bash
curl http://localhost:8000/api/v1/intelligence/<disaster_id>/recommendations
```

**Response `200` (`/recommendations`)**

```json
{
  "disaster_id": "...",
  "recommendations": [
    {
      "id": "...", "action": "deploy_ground_search_team", "target_id": "...",
      "priority": "critical", "rationale": "...",
      "supporting_evidence": ["... Evidence objects ..."],
      "uncertainty": { "level": "low", "confidence": null, "reason": "..." },
      "limitations": [], "is_simulated": true
    }
  ]
}
```

There is no ingestion endpoint yet — the only `disaster_id` this API can
currently resolve is the deterministic demo scenario's id
(`app/intelligence/demo_scenario.py::build_demo_scenario().disaster.id`,
always the same value across process restarts — see "Demo scenario,"
below). **Errors:** `404` (no disaster with that id), `422`
(`disaster_id` isn't a valid UUID).

### `GET /api/v1/analysis/{analysis_id}/intelligence[/search-zones|/recommendations]` — Analysis-Aware Intelligence

Three read-only endpoints (Milestone F3) that adapt *this* `analysis_id`'s
real damage/road-risk output into the same F2 domain model above — see
"Analysis-Aware Intelligence (Milestone F3)," below, and
[`docs/architecture/intelligence.md`](../../docs/architecture/intelligence.md)
for the full adapter design and the `analysis_id`/`disaster_id`
relationship. Distinct from `/api/v1/intelligence/{disaster_id}...`
above (which always serves the demo scenario): this path serves real
analysis-derived data, keyed by the existing `analysis_id`, never the
demo scenario.

```bash
curl http://localhost:8000/api/v1/analysis/<analysis_id>/intelligence/recommendations
```

Every response carries `context_available`/`context_unavailable_reason`
(e.g. `NO_GEOREFERENCE`, `INSUFFICIENT_EVIDENCE` — never fabricated when
evidence is missing), `roads_available`/`roads_unavailable_reason`, and
`resources_are_demo` (always `true` — no real resource-ingestion system
exists). `.../recommendations` additionally bundles
`resource_candidates` for the top-priority search zone, each with a
`route_feasibility.status` of `"computed"` (a real route, via the same
engine `POST /api/v1/routing` uses), `"route_unavailable"`, or
`"not_applicable"`. **Errors:** `404` (no analysis with that id), `422`
(`analysis_id` isn't a valid UUID).

### `GET /api/v1/analysis/{analysis_id}/summary` — AI-assisted incident briefing

Synthesizes a completed analysis's damage/road-risk/(optionally) routing
results into a short, structured operational summary — see "AI incident
intelligence," below, for the full architecture, grounding, and safety
model. Always `200` for a known `analysis_id`; every field is either a
real, deterministically-computed value or "Information unavailable." —
never an invented one. No route context (GET takes no body) — use `POST`
on the same path for that.

```bash
curl http://localhost:8000/api/v1/analysis/5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10/summary
```

**Response `200`**

```json
{
  "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10",
  "incident_severity": "high",
  "affected_structures": { "total": 12, "damaged": 9, "severely_damaged": 6, "destroyed": 2, "high_priority_count": 6 },
  "priority_area": "6 high-priority structure(s) were identified, within the approximate bounding area [20.10, 10.10] to [20.30, 10.40].",
  "route_summary": "Information unavailable.",
  "key_findings": ["12 structure(s) assessed: 9 damaged, 2 destroyed.", "Average detection confidence: 0.81."],
  "limitations": ["Damage predictions may be inaccurate.", "Road risk is a modeled estimate based on proximity to detected damage, not a verified fact.", "Road accessibility (blocked/restricted) has not been independently confirmed.", "No route was requested or available for this incident."],
  "confidence": "high",
  "generated_at": "2026-08-13T12:00:00Z",
  "source": "fallback",
  "prompt_version": "incident_summary_v1",
  "disclaimer": "This briefing is AI-assisted decision support, not a verified emergency assessment. Damage predictions may be wrong. Road risk is a modeled estimate, not a confirmed fact. Road accessibility has not been independently verified. Real emergency response decisions must rely on authoritative, verified information — not this summary alone."
}
```

`source: "fallback"` above means the configured `LLMProvider` either
isn't set (default: `deterministic`, see below) or failed/timed
out/returned malformed or unsupported output, and the deterministic
template summarizer produced this narrative instead — the response shape
is identical either way.

**Errors:** `404` (no analysis with that id), `422` (`analysis_id` isn't a
valid UUID).

### `POST /api/v1/analysis/{analysis_id}/summary` — regenerate a briefing (optional route context)

Same response shape as `GET`, with an optional `route` body to also
factor a `risk_aware`-vs-`distance_only` route comparison into the
briefing (via `RoutingService.compare_routes()`, Milestone 6C) — an empty
or absent body is equivalent to `GET`.

```bash
curl -X POST http://localhost:8000/api/v1/analysis/5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10/summary \
  -H "Content-Type: application/json" \
  -d '{
    "route": {
      "start": { "latitude": 10.0, "longitude": 20.0 },
      "destination": { "latitude": 9.99, "longitude": 20.002 }
    }
  }'
```

**Errors:** `404` (no analysis with that id), `422` (`analysis_id` isn't a
valid UUID, or `route` is present with invalid coordinates).

### Local storage

Uploaded files are written to `UPLOAD_DIR` (default `storage/uploads`,
relative to `apps/api`) under a **server-generated** name
(`<analysis_id>.<ext>`) — the client's original filename is never used to
build a filesystem path. This directory is gitignored and is a
development-only convenience; `app/services/file_storage.py` defines a
`FileStorage` protocol so it can be replaced by an S3/R2/GCS-backed
implementation later without changing `AnalysisService` or the API layer.

### Security considerations

- **Content is validated, not trusted.** Declared `Content-Type` is checked
  first as a cheap rejection, but the authoritative check is Pillow
  actually decoding the bytes and confirming the *real* format is
  supported — closing the gap where a client sends a mismatched or spoofed
  header.
- **Filenames never touch the filesystem.** Storage names are always
  server-generated (`uuid4()` + an extension derived from the
  Pillow-detected format), so path traversal via a crafted filename
  (`../../etc/passwd`) is structurally impossible, not just filtered.
- **The original filename is sanitized before being echoed back** in the
  response (`app/utils/sanitize.py`) — directory components and unsafe
  characters are stripped.
- **Size is enforced without buffering unbounded input.** The upload is
  read bounded to `MAX_UPLOAD_SIZE_MB + 1` bytes, so an oversized upload is
  rejected without ever holding the full payload in memory.
- **Uploaded files are never executed** or otherwise treated as anything
  but opaque bytes written to disk.

## Analysis lifecycle (Milestone 4)

Milestone 4 connects the upload system (Milestone 2) to the ML inference
architecture (Milestones 3A/3C) end-to-end, without fabricating any
prediction along the way.

### Status model

`AnalysisStatus` (`app/schemas/analysis.py`) is a strict enum — no
arbitrary strings ever reach the API:

```
uploaded -> queued -> processing -> completed
                                  -> failed
```

| Status | Meaning |
|---|---|
| `uploaded` | The record exists (file stored, metadata saved) but hasn't been dispatched yet. Transient — `AnalysisService.create_analysis()` and `AnalysisProcessingService.enqueue()` run back-to-back within the same request, so a client polling `GET` essentially never observes this status in practice. |
| `queued` | Dispatched for processing; not yet started. This is the status `POST /api/v1/analysis` actually returns. |
| `processing` | Inference is running right now. |
| `completed` | Inference produced a real result — `summary`/`buildings`/`model_metadata` are populated, `failure` is `null`. |
| `failed` | Inference did not produce a result — `failure` (a structured `{code, message}`) is populated, `summary`/`buildings`/`model_metadata` are `null`/empty. |

`completed` and `failed` are terminal: `AnalysisProcessingService.process()`
is a no-op if called again for an analysis already in either state (guards
against e.g. a duplicate background-task dispatch).

### Architecture: where inference logic lives

```
Route (app/api/v1/endpoints/analysis.py)
  -> AnalysisService            [Milestone 2: validate + store the upload]
  -> AnalysisProcessingService  [Milestone 4: lifecycle orchestration]
       -> DamageInferenceEngine [Milestone 3A: "Inference Service"]
            -> DamageModel      [Milestone 3C: TwoStageDamageModel]
            -> postprocessing   [Milestone 3A: build_analysis()]
       -> AnalysisRepository    [persist result/failure]
  -> DamageAnalysis             [response]
```

No inference logic lives in `app/api/`. The route only translates HTTP ↔
Pydantic and calls `AnalysisService`/`AnalysisProcessingService`; the
model, preprocessing, and postprocessing are exactly the same `app/ml/`
components Milestone 3 already built and tested — nothing ML-specific was
duplicated to wire this milestone up. `AnalysisProcessingService`
(`app/services/analysis_processing_service.py`) is the new piece: it reads
the stored image via the existing `FileStorage.load()`, calls
`DamageInferenceEngine.analyze()`, and persists the outcome via the
existing `AnalysisRepository` — it contains no model code itself.

### Model unavailable / inference failure

`AnalysisProcessingService.process()` never lets an exception escape (it
runs inside a `BackgroundTasks` callback with no HTTP client left to
respond to) and never invents a prediction to paper over a missing or
failed model. As of Milestone F4 ("Real AI Inference & Model Serving" —
see below), six distinct, precisely-mapped failure categories exist,
each caught independently rather than collapsed into one generic bucket:

- `ModelNotAvailableError` -> `AnalysisErrorCode.MODEL_UNAVAILABLE` — no
  model is configured/loaded at all (`Settings.MODEL_ENABLED=False`, or
  the legacy fine-tuned-checkpoint path with no checkpoint file).
- `ModelLoadError` -> `MODEL_LOAD_FAILURE` — a real load was *attempted*
  (e.g. downloading the pretrained CLIP checkpoint) but genuinely failed
  (no network, corrupt cache, ...) — distinct from the above.
- `InvalidImageError` -> `INVALID_IMAGE` — the stored image could not be
  decoded at inference time (defense in depth; upload-time validation
  already rejects this in the overwhelming majority of cases).
- `ImageDimensionsExceededError` -> `PREPROCESSING_FAILURE` — the image
  exceeds `Settings.MODEL_MAX_IMAGE_DIM` (a decompression-bomb guard).
- `PostprocessingError` -> `POSTPROCESSING_FAILURE` — the model's raw
  detections could not be assembled into a valid `DamageAnalysis`.
- Any other, truly unexpected exception -> the generic
  `AnalysisErrorCode.INFERENCE_FAILURE`, logged with a full traceback
  server-side (`logger.exception`). **The raw exception text/stack trace
  is never included in the API response** for any of the six.

Either way, the API stays stable: `GET /api/v1/analysis/{id}` still
returns `200` with a well-formed `DamageAnalysis` body — a structured
failure, not a `500` or a hang. **Before Milestone F4**, no
building-localization model existed at all, so every analysis through
the real, unmodified production wiring ended up `failed` with
`MODEL_UNAVAILABLE` unconditionally. **As of Milestone F4**, the default
wiring (`Settings.MODEL_ENABLED=True`, `MODEL_PROVIDER="open_clip"`)
performs genuine model inference and a real, uploaded image reaches
`completed` — see "Milestone F4 — real inference," below, for the full
architecture, and "Manual real-inference verification" for an actual
observed run. Setting `MODEL_ENABLED=false` restores the original
honest-`MODEL_UNAVAILABLE`-always behavior exactly, for an
offline/no-network deployment.

### Synchronous vs. background processing

`POST /api/v1/analysis` uses FastAPI's built-in `BackgroundTasks` to run
`AnalysisProcessingService.process()` after the response is constructed
but before the connection closes — no new infrastructure (no Redis,
Celery, or Kafka) for what's currently a single-process prototype with an
in-memory repository. `AnalysisProcessingService.process(analysis_id)`
takes only an ID and does its own lookups, so nothing about its signature
assumes *how* it's invoked — swapping `BackgroundTasks` for a real worker
(RQ/Celery/an external queue polling `queued` records) later only changes
what calls `process()`, not the service itself or anything upstream of it.
The in-memory `AnalysisRepository`'s existing `threading.Lock` (Milestone
2) already covers the concurrency this introduces — `BackgroundTasks`
callbacks run in FastAPI's threadpool, not the request's own task.

### Why fake predictions are prohibited

SentinelAI's output is meant to inform real disaster-response decisions.
A plausible-looking but fabricated damage assessment is worse than an
honest `MODEL_UNAVAILABLE` — it risks misdirecting rescue resources
towards or away from buildings no model actually assessed. Every path
through `AnalysisProcessingService.process()` that doesn't produce a real
`DamageAnalysis` from `DamageInferenceEngine` ends in `failed`, never in a
placeholder `completed`. This mirrors the same principle Milestone 3
already established for the model layer itself — see "Why predictions are
never fabricated," below — Milestone 4 just carries it through to the API.

### Example: POST then GET

```bash
$ curl -s -X POST http://localhost:8000/api/v1/analysis \
    -F "image=@aerial.jpg;type=image/jpeg" | python -m json.tool
{
    "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10",
    "status": "queued",
    "filename": "aerial.jpg"
}

$ curl -s http://localhost:8000/api/v1/analysis/5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10 | python -m json.tool
{
    "analysis_id": "5b1f8c2e-2b0a-4e9a-9c1a-3f7e6a2d9b10",
    "status": "failed",
    "summary": null,
    "buildings": [],
    "model_metadata": null,
    "failure": {
        "code": "MODEL_UNAVAILABLE",
        "message": "Stage 1 (building localization) is unavailable: No building-localization model is configured or loaded. ..."
    },
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:01Z"
}
```

By the time the second request runs, the background task has almost
always already finished (inference against an unavailable Stage 1 fails
fast) — but a client should not assume this in general; poll `GET` until
`status` is `completed` or `failed`.

## Geospatial damage intelligence (Milestone 5)

Milestone 5 adds a spatial layer on top of Milestone 4's completed
results:

```
Computer Vision -> Building Prediction -> Spatial Representation -> GeoJSON / PostGIS -> Map -> Routing (later)
```

Implemented in `app/ml/geospatial/` (a subpackage of `app/ml/`, with the
same "no FastAPI import" discipline the rest of `app/ml/` follows) plus
`app/services/spatial_repository.py` and `app/services/damage_map_service.py`
for the API-facing plumbing. See `app/ml/geospatial/__init__.py` for the
per-file breakdown.

### 1–2. Image coordinates vs. geographic coordinates, and why GPS is never invented

An ordinary JPEG/PNG/WEBP — the only formats `POST /api/v1/analysis`
accepts — carries **pixel coordinates only**: `x`/`y` positions relative to
the top-left corner of the image file itself. It does not inherently know
where on Earth it was taken. Latitude and longitude are a *different*
coordinate system entirely, requiring separate metadata (a geotransform, a
declared CRS — see "CRS handling," below) that ordinary consumer image
formats don't carry.

Treating a pixel coordinate as if it were a geographic one — e.g. reading
`x=100, y=200` as `latitude=100, longitude=200` — is not a rounding error,
it's a **fabricated GPS coordinate**: a plausible-looking but meaningless
number that could misdirect a real rescue effort if plotted on a map and
trusted. SentinelAI's research-integrity principle from Milestone 3
("never fabricate a prediction") applies exactly the same way here to
*location*: every `BuildingDamage.geometry` is paired with an explicit
`georeferenced: bool` (`app/ml/schemas.py`), and nothing in this codebase
ever sets `georeferenced=True` without a real transform (see
"Georeferenced mode," below) having actually produced the coordinates.

### 3. Image-space mode

This is the **only mode this codebase's production wiring actually
produces today** — see "Limitations of ordinary JPEG uploads," below, for
why. `app.ml.geospatial.spatial_builder.image_space_geometry` takes a
detection's pixel `BoundingBox` (from `app.ml.model.RawDetection`, Stage 1
of the ML pipeline — see "ML architecture," below) and wraps it as a
`BoundingBoxGeometry` with:

- `coordinate_reference_system = CoordinateReferenceSystem.IMAGE` (not a
  real CRS — an explicit "these are pixels" marker, see "CRS handling,"
  below)
- `georeferenced = False`

`app.ml.postprocessing.build_analysis` calls this for every detection, so
every `BuildingDamage` produced by this codebase carries these fields
today. A building with no location at all (`bounding_box is None` — every
detection Stage 2 alone produces, since it only classifies a known crop)
gets `geometry = None` too — no location means no geometry, never an
invented one.

### 4. GeoJSON representation

`app/ml/geospatial/geojson.py` converts `BuildingDamage` predictions into
standard GeoJSON (RFC 7946) `Feature`/`FeatureCollection` objects —
deliberately the same format Leaflet/Mapbox/MapLibre already consume,
not a custom map format (see "Frontend contract," below).

- Only buildings with `geometry is not None` become features; the rest are
  silently excluded (never given an invented point/box).
- `Feature.properties` carries exactly five fields:
  `building_id`, `damage_class`, `confidence`, `priority`
  (see "Damage-based priority," below), and `georeferenced` — no model
  internals (raw logits, model name, ...) leak into map-facing output.
- GeoJSON has no dedicated "bounding box" geometry type (RFC 7946's
  geometry types are Point/LineString/Polygon/Multi*/GeometryCollection);
  this codebase's own `BoundingBoxGeometry` is rendered as a closed,
  five-position rectangular `Polygon` — a correct GeoJSON representation
  of the same rectangle, not an approximation.
- `FeatureCollection.coordinate_reference_system` is a foreign member
  (RFC 7946 §6.1 explicitly allows, and expects consumers to ignore,
  members outside the spec) carrying the shared CRS for every feature in
  one analysis's collection.

**Image-space GeoJSON is still valid GeoJSON syntax, but its coordinates
are not geographic** — always check `properties.georeferenced` (or the
collection's `coordinate_reference_system`) before plotting a
`FeatureCollection` on a real map. This is why the "damage-map API"
response wraps the `FeatureCollection` in an `available`/`reason` envelope
(`app/schemas/damage_map.py`) rather than handing back bare GeoJSON —
`available=False` makes "there's nothing meaningful to plot yet" an
explicit, typed fact instead of something a consumer has to infer from an
empty `features` array alone.

### Georeferenced mode

`app/ml/geospatial/georeferencing.py` defines the abstraction for turning
pixel coordinates into real geographic ones:

- `GeoreferencingTransform` — maps one specific image's pixel coordinates
  into geographic coordinates (`transform_point`/`transform_bounding_box`).
- `AffineGeoTransform` — a real, correct implementation of GDAL's standard
  six-parameter geotransform convention (`geo_x = a + col*b + row*c`,
  `geo_y = d + col*e + row*f`) — exactly what a GeoTIFF's own geotransform
  provides. Fully implemented and tested; **nothing in this milestone
  constructs one with real data**, since no image source that actually
  carries this metadata is ingested yet.
- `GeoreferencingProvider` — looks up the transform for a stored image.
  `NoGeoreferencingAvailable` is the only implementation wired into
  production DI, and it **always raises** `GeoreferencingUnavailableError`
  — never a guessed transform, and never silently returns a
  non-georeferenced result behind the caller's back (see
  `app.ml.geospatial.spatial_builder.georeferenced_geometry`, which is
  ready to call once a real provider exists, but isn't wired into
  `build_analysis` yet).

This mirrors the exact honesty pattern `UnavailableBuildingLocalizer` /
`UnavailableDamageModel` already established in Milestone 3: real,
tested infrastructure for the transformation *math*, with no default
implementation that fabricates a result when real metadata is missing.

### CRS handling

`app/ml/geospatial/crs.py`'s `CoordinateReferenceSystem` makes every
geometry's coordinate system explicit rather than assumed:

- `IMAGE` — not a real-world CRS; this codebase's own marker for "pixel
  coordinates, no geographic meaning."
- `WGS84` (`EPSG:4326`, longitude/latitude) — the only real geographic CRS
  supported today, and the one RFC 7946 (GeoJSON) and every mapping
  library in the frontend contract expect.

Why this matters: a bare `(x, y)` pair is meaningless without knowing its
CRS — pixel coordinates and WGS84 degrees are both just floats in
overlapping numeric ranges for a small image, so conflating them silently
is exactly how a fabricated GPS coordinate would happen by accident. The
intended future pipeline:

```
source CRS -> coordinate transformation -> WGS84 -> GeoJSON / mapping
```

A future `source CRS` (a UTM zone, State Plane, whatever a real GeoTIFF
declares) needs reprojection into WGS84 before reaching GeoJSON — that
needs a real geodesy library (e.g. `pyproj`), deliberately not added this
milestone. `validate_crs()` and `UnsupportedCRSError` reject any CRS
string outside `{IMAGE, WGS84}` today rather than silently accepting one
this codebase can't actually handle correctly — `AffineGeoTransform`
itself refuses construction with `source_crs != WGS84` for the same
reason.

### 5. Damage-based priority

`app/ml/geospatial/priority.py`'s `compute_damage_priority()` is a
deterministic function of `DamageClass` alone:
`destroyed (critical) > major (high) > minor (medium) > no_damage (low)`.

**Explicitly labeled damage-based priority — not a complete
emergency-response prioritization model.** A real triage priority would
also need:

- population (how many people are near/in the building)
- proximity to hospitals, schools, and other critical infrastructure
- road accessibility (can rescue crews actually reach it)
- hazard risk (aftershocks, flooding, fire spread, structural collapse)
- prediction uncertainty (a low-confidence "destroyed" call shouldn't
  outrank a high-confidence one)

None of that data exists in this codebase yet, so none of it factors into
`priority` today. `priority` is computed at read time (GeoJSON conversion,
spatial queries) rather than stored — it's a pure function of
`damage_class`, not independent state that could drift out of sync with it.

### 6. Future PostGIS architecture

`app/services/spatial_repository.py`'s `SpatialRepository` Protocol (with
`InMemorySpatialRepository` as its only implementation, mirroring
`AnalysisRepository`'s own current tradeoff) is the seam a real PostGIS
implementation fills later, **without introducing a database now** — this
milestone stays in-memory, matching the rest of this codebase's
persistence so far.

Deliberately a separate repository from `AnalysisRepository`: in a
normalized PostGIS schema, an analysis's building geometries would live in
their own `buildings` table (one row per building, a real `geometry`/
`geography` column with a spatial index) rather than embedded in the
`analyses` row. `SpatialRepository` already reflects that split, so a
future PostGIS implementation changes no caller
(`AnalysisProcessingService`, `DamageMapService`):

| Method | Future PostGIS equivalent |
|---|---|
| `save_buildings` | `INSERT`/`UPSERT` into `buildings`, ideally in the same transaction as the analysis's `completed` write |
| `get_buildings` | `SELECT * FROM buildings WHERE analysis_id = :id` |
| `get_damaged_buildings` | `... WHERE damage_class != 'no_damage'` |
| `get_severely_damaged_buildings` | `... WHERE damage_class IN ('major', 'destroyed')` |
| `get_buildings_in_bounding_box` | `... WHERE ST_Intersects(geometry, :bbox)` |
| `get_high_priority_buildings` | `... WHERE priority_rank >= :threshold ORDER BY priority_rank DESC` |

Every query is scoped to one `analysis_id` — there are no cross-analysis
spatial queries yet (e.g. "all damaged buildings across every uploaded
image in a region"), a natural PostGIS extension once there's a real use
case, not implemented speculatively here.

### 7. Future integration with OpenStreetMap

Not implemented this milestone (see "Important," the task boundary, below)
— noted here as the natural next step once real georeferenced geometry
exists. Once `georeferenced=True` `BuildingDamage`s exist, the intended
path is: georeferenced building geometry -> spatially joined against
OpenStreetMap's road network (e.g. via `osmnx`/a local OSM extract loaded
into PostGIS) -> routing graph -> rescue-route computation. This is
explicitly Milestone 6+ territory — this milestone only prepares the
geometry OSM integration would eventually consume.

### 8. Limitations of ordinary JPEG uploads

`POST /api/v1/analysis` accepts JPEG/PNG/WEBP — ordinary consumer image
formats. None of them carry:

- a geotransform (the pixel -> geographic coordinate mapping)
- a declared CRS
- ground sample distance / pixel resolution in real-world units

A photo *might* carry EXIF GPS tags, but that's a single camera location
(where the photo was taken from), not a per-pixel mapping from image
coordinates to geographic coordinates — not the same thing as
georeferencing metadata, and not currently read by this codebase anyway.
This is why `NoGeoreferencingAvailable` (see "Georeferenced mode," above)
is the only `GeoreferencingProvider` wired into production DI: it's not a
gap to be filled by trying harder with a JPEG, it's a structural property
of the file format.

### 9. Requirements for true geospatial satellite imagery

Real georeferencing needs imagery in a format that actually carries
spatial metadata — most commonly **GeoTIFF** (or another raster format
with an embedded or sidecar geotransform + CRS, such as a `.tfw` world
file). Concretely, this pipeline would need:

1. **A raster format carrying its own geotransform** — GeoTIFF's six
   affine parameters (exactly what `AffineGeoTransform` already
   implements the math for) plus a declared CRS (often UTM for satellite
   imagery, not WGS84 — see "CRS handling," above, for why that then needs
   reprojection).
2. **An ingestion path that reads that metadata** — not implemented yet;
   `POST /api/v1/analysis` today only decodes pixels via Pillow (see
   `app/services/image_validation.py`), which discards any such metadata
   even if present.
3. **A `GeoreferencingProvider` implementation that constructs a real
   `AffineGeoTransform` (or equivalent) from that metadata** per uploaded
   image, replacing `NoGeoreferencingAvailable` for that image.
4. **A reprojection step** (a real geodesy library, e.g. `pyproj`) if the
   source imagery's CRS isn't already WGS84.

Until all four exist for a given upload, the honest result is
`georeferenced=False` image-space geometry — which is exactly what this
milestone produces, and exactly why it produces it.

## Road network (Milestone 6A)

Milestone 6A builds the road-network **foundation** future emergency
rescue routing will need:

```
OpenStreetMap -> Road Network -> Graph -> Risk-weighted Graph -> Rescue Routing
```

This milestone builds only the first two arrows. **No shortest-path
routing (Dijkstra, A*, or otherwise) is implemented** — see "Do not
implement," below. Implemented in `app/roads/` (a subpackage of `app/`,
with the same "no FastAPI import" discipline `app/ml/` follows) plus
`app/services/road_network_repository.py`,
`app/services/road_network_ingestion_service.py`, and
`app/services/road_network_status_service.py` for the DI-facing plumbing.
See `app/roads/__init__.py` for the per-file breakdown.

### Why a graph representation

A road network is naturally a graph: a **node** is a location or
intersection — a point where a route can start, end, or change direction.
An **edge** is a traversable road segment connecting two nodes. A
**weight** is the cost of traversing that edge. This is the standard
representation every real shortest-path/navigation algorithm (Dijkstra,
A*, and every production routing system) is built on — disaster-response
routing doesn't change that representation, only what the weight means.

Directed edges are required, not optional: many real roads are one-way,
so "can I get from A to B" is not always the same question as "can I get
from B to A." Only a directed graph can express that correctly — an
undirected graph would silently permit illegal-direction routes, which is
exactly the kind of wrong answer a rescue-routing system cannot afford.

The future weight formula, once damage/hazard intelligence exists to feed
it:

```
weight = distance + damage_risk + hazard_risk + blockage_penalty
```

Milestone 6A implements only `weight = distance` (as `base_cost` — see
"Graph weights," below). `RoadEdge` already carries the fields
(`risk_score`, `accessibility`) a later milestone will populate — never
fabricated placeholders today.

### OSM data source: the Overpass API

[OpenStreetMap](https://www.openstreetmap.org)'s
[Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API) is the
official, appropriate mechanism for extracting a bounded subset of OSM
data (not scraping a website — it's a purpose-built query API for exactly
this use case). `app/roads/osm_source.py` implements
`OverpassRoadNetworkSource` against it, using the standard library's
`urllib.request` rather than adding a new HTTP client dependency for one
call site.

**No new heavy geospatial dependency was added.** `osmnx`/`geopandas`/
`shapely` were considered and deliberately not used — this milestone
doesn't yet need shortest-path algorithms (out of scope, see "Do not
implement") or polygon geometry operations, and this codebase has already
established the pattern of deferring a geometry library until something
actually needs it (`app.ml.datasets.schemas`'s `polygon_wkt`, Milestone
5's deferred `shapely`/`pyproj`). The graph itself is a hand-rolled,
dict-based structure behind `RoadNetworkRepository` (see below) — small
enough that reimplementing it was simpler and lighter than adding
`networkx` for operations (add/get/neighbors) it would barely use yet. If
a later milestone needs real shortest-path algorithms, `networkx` (or
similar) is the natural choice then — deferred, not fabricated.

### Separation of concerns

Three deliberately separate stages, matching the "Separate: OSM data
acquisition / from graph construction / from routing" requirement:

1. **OSM data acquisition** (`app/roads/osm_source.py`) —
   `RoadNetworkSource` Protocol + `OverpassRoadNetworkSource`. Fetches and
   parses raw OSM JSON into `OSMNode`/`OSMWay`/`OSMRoadData`. Knows
   nothing about graphs, edges, or cost.
2. **Graph construction** (`app/roads/builder.py`) —
   `build_road_network(data, repository)`. Turns `OSMRoadData` into
   `RoadNode`/`RoadEdge` records and populates a `RoadNetworkRepository`.
   Doesn't know or care whether `OSMRoadData` came from a live Overpass
   call or a static test fixture.
3. **Routing** — not implemented this milestone.

`parse_overpass_response()` (in `osm_source.py`) is a pure function with
no network access — this is what the test suite exercises directly,
against a small static fixture shaped exactly like a real Overpass API
response, so **the entire test suite runs with zero internet access**.
`OverpassRoadNetworkSource.fetch_bounding_box()` — the only thing that
actually makes a network call — is never invoked by the application at
startup, by any route, or by any test.

### Node model

`RoadNode` (`app/roads/schemas.py`): `node_id`, `latitude`, `longitude`.
Coordinate validity reuses Milestone 5 directly rather than duplicating
validation logic: `RoadNode.geometry` is a real
`app.ml.geospatial.geometry.PointGeometry` (GeoJSON coordinate order,
`(longitude, latitude)`), and out-of-range or non-finite coordinates raise
the same `InvalidGeometryError` Milestone 5 already established — this
package doesn't invent a parallel coordinate-validation error.

### Edge model

`RoadEdge` (`app/roads/schemas.py`) is always directed —
`source_node`/`target_node` — with:

| Field | Notes |
|---|---|
| `distance` | Meters; must be positive and finite (`InvalidRoadGraphError` otherwise). Computed via the haversine formula (`app/roads/geo_utils.py`) — a real great-circle calculation, not an approximation or a fabricated value. |
| `base_cost` | Today: exactly `distance` — see "Graph weights," below. |
| `road_type` | Raw OSM `highway` tag value, passed through unmodified — not mapped into an invented closed taxonomy (OSM's `highway` vocabulary is large and evolving; inventing a subset enum risks silently dropping real values). `None` if untagged. |
| `name`, `maxspeed`, `surface` | Raw OSM tag values, `None` if untagged. `maxspeed` is kept as the raw string (units vary by country/tag convention) — not parsed or unit-converted. |
| `lanes` | Parsed to `int` when the OSM tag is a clean integer; `None` for anything else (e.g. `"2;3"`, a lane count that changes along the way) — never a guessed number. |
| `one_way` | From OSM's `oneway` tag (`yes`/`true`/`1`). |
| `accessibility` | See "Accessibility," below. |
| `risk_score` | Always `None` from OSM ingestion — OSM has no concept of disaster risk. See "Graph weights," below. |

A two-way OSM way becomes **two** `RoadEdge`s (one per direction, both
`one_way=False`) — `RoadEdge` itself is always a single direction; there
is no separate undirected representation anywhere in this codebase.

### Accessibility model

`AccessibilityStatus`: `open` / `restricted` / `blocked` / `unknown`.
**OSM ingestion always sets `unknown`** — `app/roads/builder.py` never
inspects OSM's own `access`/`barrier` tags to infer `restricted` or
`blocked` this milestone, and never sets `blocked` from OSM data under any
circumstance. This is a deliberate, conservative choice: OpenStreetMap is
a static basemap with no knowledge of an ongoing disaster, so "OSM data
alone should not determine disaster blockage." A future milestone derives
real `blocked`/`restricted` status from SentinelAI's own damage/hazard
intelligence (Milestone 5's `BuildingDamage`/`DamagePriority`, and later
hazard prediction) and overlays it onto the graph.

### Graph weights

Every `RoadEdge.base_cost` is computed by
`app.roads.weighting.compute_base_cost()` — today, the identity function
(`base_cost = distance`). This is a deliberately tiny, separately tested
function, called explicitly by every edge-construction call site
(`app/roads/builder.py`, test fixtures) rather than hidden inside a model
validator, so it's obvious exactly where "distance becomes cost" happens
and easy to extend later:

```
weight (future) = distance + damage_risk + hazard_risk + blockage_penalty
```

**No damage risk is applied yet.** `risk_score` and `accessibility` exist
on every edge specifically so a future risk-aware weighting stage can
read and combine them with `base_cost` — without another schema change.

### Graph abstraction

`RoadNetworkRepository` (`app/services/road_network_repository.py`) —
same Protocol-based swap pattern as `AnalysisRepository`/
`SpatialRepository`: `add_node`, `add_edge`, `get_node`, `get_edge`,
`neighbors`, `get_graph` (a full snapshot), `get_bounds`, and
`query_bounding_box` (reusing `app.ml.geospatial.geometry.BoundingBoxGeometry`
directly — `(min_lon, min_lat, max_lon, max_lat)`, the same convention
`RoadNode.geometry`'s coordinate order already follows).

Nothing outside this module (or `app/roads/`) ever sees a raw graph-library
object or a bare dict — every caller depends on `RoadNode`/`RoadEdge`/
`RoadGraph`. `InMemoryRoadNetworkRepository` is the only implementation
today (process-local, non-persistent, same tradeoff as
`InMemoryAnalysisRepository`); a future PostGIS + pgRouting-backed
implementation would replace it without changing any caller.

`add_edge()` is strictly directed and raises `UnknownRoadNodeError` if
either endpoint hasn't been added via `add_node()` first — a two-way road
is represented by *two* directed edges added explicitly by the caller
(`app/roads/builder.py`); the repository never infers or auto-adds a
reverse edge.

### Data ingestion

`RoadNetworkIngestionService` (`app/services/road_network_ingestion_service.py`)
is the seam a future explicit command — `load road network for bounding
box`, a CLI command or an admin-only endpoint, neither implemented this
milestone — would call: OSM acquisition -> graph construction ->
repository, in one call. **No application startup or route downloads OSM
data automatically**, and no large dataset is ever fetched without an
explicit, bounded request. `app/api/deps.py` wires the real
`OverpassRoadNetworkSource` into DI (mirroring how `BuildingLocalizerDep`
was wired before any route used it in Milestone 3) so the seam is real
and testable, even though nothing calls it yet.

### Offline development and testing

Every test in `tests/test_roads.py` runs with zero internet access,
zero GPU, and is fully deterministic:

- **Deterministic synthetic road-network fixtures** — a small four-node
  square (matching the milestone's own example: `A -- B -- C` / `|` /
  `D --------`), built directly via `RoadNode`/`RoadEdge` and
  `InMemoryRoadNetworkRepository`, no OSM involved.
- **A synthetic Overpass-shaped JSON fixture** — a small, hand-written
  dict with the same `elements: [{type: node/way, ...}]` shape a real
  Overpass API response has, exercised through the real
  `parse_overpass_response()` parser.
- **`OverpassRoadNetworkSource`'s error-handling path** — tested by
  patching `urllib.request.urlopen` to fail immediately, proving
  `RoadNetworkSourceError` propagates correctly without ever touching the
  network.

### Do not implement (this milestone)

Shortest-path routing, A*, Dijkstra, route optimization,
damage-to-road intersection, hazard prediction, tsunami prediction, LLM
summaries, a frontend map, or 3D visualization. All later milestones.

## Road risk model (Milestone 6B)

Milestone 6B connects Milestone 5's geospatial damage predictions to
Milestone 6A's road graph:

```
Damage Geometry + Road Geometry -> Spatial Analysis -> Road Risk -> Risk-aware Road Graph
```

**No route optimization, shortest-path routing, or live navigation is
implemented** — see "Do not implement," below. Implemented in `app/risk/`
(a new subpackage, the bridge between `app/ml/geospatial` and
`app/roads/` — see `app/risk/__init__.py`) plus
`app/services/road_risk_service.py` for the DI-facing plumbing.

### Core principle: four distinct things, not one

A damaged building near a road does not automatically mean the road is
blocked. This milestone always keeps four concepts separate rather than
collapsing them into one number:

1. **Damage severity** — `BuildingDamage.damage_class`. A property of one
   building.
2. **Proximity to damage** — `RiskSource.distance_meters`. A purely
   geometric fact.
3. **Road risk** — `RoadEdge.risk_score`/`risk_level`. A *derived
   estimate* combining (1), (2), and confidence.
4. **Road blockage** — `RoadEdge.accessibility`. A *separate* field this
   milestone never sets from risk.

### The baseline heuristic formula

```
risk contribution = severity_weight(damage_class) x distance_decay(distance) x confidence
```

**This is a deterministic, explainable baseline heuristic risk model —
not a scientifically validated one.** It has not been calibrated or
evaluated against real disaster data (see "Future research," below, for
what real validation would require). Every constant is centralized on
`Settings` (`ROAD_RISK_*` fields, `app/core/config.py`) and assembled into
a typed, validated `RoadRiskConfig` (`app/risk/config.py`) — nothing in
`app/risk/` hardcodes a weight or threshold inline.

**Why proximity matters:** damage further from a road is less likely to
affect it — a destroyed building 500m away isn't a reason to avoid a
road; one 5m away plausibly is. `distance_decay(d) = exp(-decay_rate * d)`
is smooth and monotonic (no discontinuity at some arbitrary cutoff),
governed by one interpretable parameter: its half-life,
`ln(2) / decay_rate` meters (≈35m at the default `0.02`/meter).

**Why damage severity matters:** a road next to a destroyed building is
plausibly more affected (debris, structural collapse onto the roadway,
downed utilities) than one next to minor damage. Severity weights reuse
the existing `DamageClass` taxonomy — **no second damage taxonomy** —
with an ordinal scale, defaulting to:

| `DamageClass` | Weight | Setting |
|---|---|---|
| `no_damage` | `0.0` | `ROAD_RISK_SEVERITY_WEIGHT_NO_DAMAGE` |
| `minor` | `0.25` | `ROAD_RISK_SEVERITY_WEIGHT_MINOR` |
| `major` | `0.6` | `ROAD_RISK_SEVERITY_WEIGHT_MAJOR` |
| `destroyed` | `1.0` | `ROAD_RISK_SEVERITY_WEIGHT_DESTROYED` |

**Why confidence can affect risk:** a low-confidence detection is less
trustworthy evidence than a high-confidence one. `confidence` is already
a well-defined `[0, 1]` field on every `BuildingDamage`; multiplying by it
lets uncertain detections contribute proportionally less, without
discarding them outright.

**Why risk is not equivalent to blockage:** risk is a continuous estimate
of *plausible impact*; blockage is a factual claim about *whether a
vehicle can currently pass*. A `critical`-risk edge is not automatically
`blocked` — confirming blockage needs stronger evidence (an actual
observation, a later milestone's job) than "there's a destroyed building
nearby." Treating them as the same field would either under-warn (marking
genuinely impassable roads merely `high`) or over-block (closing routes
that are risky-looking but still passable) — see "Accessibility is
independent of risk," below.

### Distance method

**Distance is never computed from raw latitude/longitude degrees.** A
degree of longitude spans a different physical distance depending on
latitude (shrinking to zero at the poles), so subtracting raw coordinates
and calling the result "distance" would silently distort every
measurement away from the equator.

`app/risk/spatial.py`'s `point_to_segment_distance_meters()` instead
projects the damage point and the road segment into a **local
tangent-plane (equirectangular) approximation** centered on the query
point, converting angular offsets into meters using the same
spherical-Earth model `app.roads.geo_utils`'s haversine distance already
uses (Milestone 6A) — one consistent Earth model across both milestones,
not two different ones. This is an appropriate, standard simplification
at the scale this analysis runs at (individual road segments up to a few
hundred meters); it is **not** a survey-grade geodesic calculation and is
not claimed to be one. Reprojecting into a real projected CRS (e.g. UTM,
via `pyproj`) is the natural upgrade path once this needs to be accurate
at larger scales or near the poles — deliberately not added now, matching
this codebase's established pattern of deferring geodesy libraries
(Milestone 5's `pyproj` deferral) until something actually needs them.

Distance is computed **point-to-segment** (the closest point anywhere
along the road edge, clamped to the segment itself), not merely
point-to-nearest-endpoint — a building near the midpoint of a long edge
is correctly recognized as close, not missed because it isn't near either
node.

**CRS is never mixed.** Only buildings with `georeferenced=True` and
`coordinate_reference_system == WGS84` are ever considered — a
pixel-space (`georeferenced=False`) building is excluded outright,
*regardless of how numerically close its raw coordinates happen to look
to a road node's lat/lon* (tested explicitly — see "Tests," below). Since
no real georeferencing pipeline exists yet (Milestone 5), **every
analysis through the real, unmodified production pipeline today has zero
georeferenced buildings** — so `GET .../road-risk` will honestly report
`available=false` until a real georeferencing source exists. This is
expected, not a bug (see "Missing spatial data," below). The road graph
itself is always real WGS84 (`RoadNode`), so its CRS is preserved as-is
throughout — nothing reprojects road coordinates.

### Spatial relationship pipeline

For each road edge (`app/risk/analyzer.py`'s `compute_road_risk`):

1. **Obtain its geometry** — its two endpoint `RoadNode`s.
2. **Find nearby damage geometries** — a coarse bounding-box pre-filter
   (`app/risk/spatial.py`'s `padded_bounding_box`, reusing
   `app.ml.geospatial.geometry.BoundingBoxGeometry` directly), padded by
   `ROAD_RISK_SEARCH_RADIUS_METERS` (default `150.0`).
3. **Calculate distance** — the exact point-to-segment distance for every
   candidate that survived the pre-filter; anything beyond the search
   radius is excluded.
4. **Calculate damage contribution** — the formula above, per candidate.
5. **Aggregate contributions** — see "Risk aggregation and normalization,"
   below.
6. **Produce road risk** — a **copy** of the edge (`model_copy`) with
   `risk_score`/`risk_level`/`risk_sources` populated.

**Original damage predictions are never modified** — every `BuildingDamage`
is only ever read. **No coordinates are ever invented** — a building with
no geometry, or one whose geometry can't be resolved to a representative
point, is silently skipped, never assigned a guessed location.

### Spatial indexing

`compute_road_risk`'s `find_nearby_buildings` parameter is the
spatial-indexing seam: a `BoundingBoxGeometry -> Sequence[BuildingDamage]`
callback, not a hardcoded O(N×M) nested loop over every edge against
every building. Production wiring (`RoadRiskService`) implements it as a
simple filter over an already CRS-filtered building list — appropriate
for a prototype's small in-memory data — but the *interface* is exactly
what a future PostGIS-backed implementation (`ST_DWithin` against a
spatial index) would plug into unchanged, without `analyzer.py` itself
needing to change.

### Risk aggregation and normalization

`app/risk/formula.py`'s `aggregate_contributions()`: **sum every
contribution, then cap** to `ROAD_RISK_AGGREGATION_CAP` (default `1.0`).

A plain sum — not a maximum, and not a probabilistic combination like
"noisy-OR" — so multiple nearby damaged buildings compound risk rather
than the single worst one dominating: simple, easy to explain to a
non-technical responder ("three moderately-damaged buildings nearby added
up"), and monotonic (adding another damaged building never lowers risk).
The cap prevents unbounded accumulation — without it, a cluster of ten
destroyed buildings could report a risk score of `6` or more, meaningless
once risk is meant to read as "0 = none, 1 = maximal."

### Risk levels

`RiskLevel`: `low` / `moderate` / `high` / `critical`, from centrally
configured thresholds (`ROAD_RISK_LEVEL_LOW_MAX`/`_MODERATE_MAX`/`_HIGH_MAX`,
defaulting to an even quartile split at `0.25`/`0.5`/`0.75`).
**Engineering categories, not validated emergency-management risk
classes.**

### Risk source representation

Every `RiskSource` (`app/roads/schemas.py`) carries `building_id`,
`damage_class`, `confidence`, `distance_meters`, and `contribution` — the
architecture's explainability requirement: a responder should eventually
be able to see *why* a road is considered risky, not just a bare number.
**Risk sources are never fabricated** — only ever produced from a real,
georeferenced `BuildingDamage` actually found within the configured
search radius of the edge; damage outside that radius, or with no usable
geometry, never appears.

### Road graph changes

`RoadEdge` (`app/roads/schemas.py`) is **extended, not duplicated** — no
second road graph. It already had `base_cost`/`risk_score`/`accessibility`
(Milestone 6A, reserved for exactly this); Milestone 6B adds `risk_level`
and `risk_sources`. `app/risk/formula.py`'s `compute_risk_adjusted_cost()`
derives a risk-adjusted cost as a **pure function**, not a stored field
(avoiding a redundant value that could drift from `base_cost`/`risk_score`):

```
risk_adjusted_cost = base_cost x (1 + cost_penalty_scale x risk_score)
```

`cost_penalty_scale` (`ROAD_RISK_COST_PENALTY_SCALE`, default `4.0`) is
configurable; `risk_score is None` (never assessed) leaves `base_cost`
unchanged. **No routing algorithm consumes this yet.**

### Accessibility is independent of risk

`compute_road_risk` never touches `RoadEdge.accessibility` — every
risk-assessed edge is a `model_copy` updating only
`risk_score`/`risk_level`/`risk_sources`. A road can be
`risk_level=critical` and `accessibility=open` simultaneously (tested
explicitly) — for this milestone, accessibility only ever changes via
whatever set it originally (OSM ingestion always leaves it `unknown`, see
Milestone 6A). A future evidence source (a confirmed observation, a
stronger hazard signal) is what would actually change accessibility —
proximity to damage alone never does, no matter how high the computed
risk.

### Missing spatial data

`GET /api/v1/analysis/{id}/road-risk` reports `available=false` (never a
fabricated assessment) for any of:

- The analysis isn't `completed` yet.
- The analysis has no georeferenced (WGS84) damage geometry — the honest,
  expected state for every analysis today (see "Distance method," above).
- No road network is loaded (see `GET /api/v1/roads/status`).

### Tests

`tests/test_road_risk.py` covers the formula (severity ordering, distance
decay, confidence scaling, aggregation, capping, level classification,
risk-adjusted cost), the spatial math (point-to-segment distance including
degenerate segments, bounding-box padding, representative points for each
geometry type), the full `compute_road_risk` pipeline (no/minor/major/
destroyed damage, multiple sources, far-away exclusion, unmutated
originals, accessibility independence), `RoadRiskService`'s three
"unavailable" branches, and the full HTTP endpoint — all with synthetic,
deterministic coordinates; zero internet access, zero GPU.

### Future research

Not implemented — documented as the natural next steps once real data
exists:

- Flood extent, landslide susceptibility, earthquake intensity
- Road closure observations (ground-truth blockage evidence)
- Elevation, bridge damage, weather
- Historical disaster data
- Uncertainty calibration (today's `confidence` is a raw model output,
  not a calibrated probability — see Milestone 3C's own "Confidence
  interpretation" limitation, which applies equally here)
- A learned risk function (replacing this heuristic once labeled
  road-outcome data exists to train and validate one)
- Probabilistic routing (routing that reasons about risk *distributions*,
  not a single deterministic score)

### Do not implement (this milestone)

Dijkstra, A*, route optimization, live navigation, hazard prediction,
tsunami prediction, LLM summaries, frontend changes, or 3D visualization.
All later milestones.

## Risk-aware rescue routing (Milestone 6C)

Milestone 6C closes the loop from Milestones 6A/6B:

```
Damage Intelligence + Road Graph + Risk Model -> Routing Engine -> Route Result
```

**No route optimization, live navigation, traffic prediction, or
real-time vehicle tracking is implemented** — see "Do not implement,"
below. Implemented in `app/routing/` (the bridge between `app.roads` and
`app.risk`, consuming both — see `app/routing/__init__.py`) plus
`app/services/routing_service.py` for the DI-facing plumbing.

### Routing algorithm

**Dijkstra's algorithm, via a binary heap.** Both edge-cost formulas this
milestone uses (`base_cost`, and the risk-adjusted cost from Milestone
6B) are always non-negative, so Dijkstra is directly applicable and
provably optimal — the simplest algorithm appropriate for that property.

The same implementation *is* A* when given a heuristic (Dijkstra is
exactly A* with a heuristic that always returns zero) —
`RoutingConfig.use_astar_heuristic` (default `False`) switches to A* with
`haversine_heuristic()` (straight-line distance to the destination).
This heuristic is **admissible** for both cost formulas: a real road
distance is never shorter than the straight-line distance between the
same two points, and the risk-adjusted/accessibility-penalized cost is
never less than the base distance cost (every multiplier is `>= 1`) — so
admissibility for `base_cost` implies admissibility for the derived costs
too. **This does not mean A* is always superior** — for prototype-scale
graphs, Dijkstra's extra node expansions are negligible, and Dijkstra's
correctness doesn't depend on an admissibility proof remaining valid as
the cost formula evolves; A* is an available, tested optimization, not
the default. `tests/test_routing.py` verifies both configurations agree
on the same optimal path and cost.

**The architecture allows the algorithm to be replaced later**:
`shortest_path()` takes a `PathfindingGraph`-shaped object (`get_node`/
`neighbors`/`get_edge`) and an edge-cost function — any algorithm
satisfying that shape (a real graph library's optimized implementation,
a bidirectional search, ...) can replace it without any caller changing.

### Distance cost (`distance_only`)

Minimizes `RoadEdge.base_cost` alone (today: exactly `distance`, from
Milestone 6A) — the control condition: what a routing engine ignorant of
any damage/risk would produce.

### Risk cost (`risk_aware`)

```
risk_adjusted_cost = base_cost x (1 + risk_penalty x risk_score)
```

**Reuses `app.risk.formula.compute_risk_adjusted_cost` unmodified** —
Milestone 6B's own formula (`risk_penalty` = `ROAD_RISK_COST_PENALTY_SCALE`),
not a second, silently different one. Layered with the accessibility
penalty below, applied identically in both modes (see "Accessibility
behavior").

Both modes' coefficients are centralized: `RoutingConfig`
(`app/routing/config.py`), sourced from `Settings`' `ROUTING_*` fields —
nothing in `app/routing/` hardcodes a coefficient inline.

| Setting | Default | Meaning |
|---|---|---|
| `ROUTING_RESTRICTED_ACCESSIBILITY_PENALTY` | `0.5` | Cost multiplier added for `restricted` edges (both modes). |
| `ROUTING_UNKNOWN_ACCESSIBILITY_POLICY` | `"open"` | How `unknown`-accessibility edges are treated (see below). |
| `ROUTING_MAX_SNAP_DISTANCE_METERS` | `500.0` | Farthest a coordinate may snap to a graph node before it's treated as "no nearby node." |
| `ROUTING_USE_ASTAR_HEURISTIC` | `False` | `True` switches Dijkstra to A* with the haversine heuristic. |

### Accessibility behavior

Kept a genuinely separate concept from risk — a `critical`-risk edge is
never automatically reclassified as `blocked`:

| `AccessibilityStatus` | Routing behavior |
|---|---|
| `open` | Traversable, no penalty. |
| `restricted` | Traversable, with the configured cost penalty (both modes). |
| `blocked` | **Not traversable** — excluded from the search entirely (never assigned merely a high cost). |
| `unknown` | Follows `ROUTING_UNKNOWN_ACCESSIBILITY_POLICY` (default: treated as `open`). |

`unknown` defaults to `open` because OSM ingestion (Milestone 6A) always
leaves every edge in that state — treating the *entire* graph as
blocked-by-default would make routing unusable against today's honest,
real state, where nothing has confirmed accessibility yet. A more
conservative deployment can override this via `Settings`.

### Nearest-node strategy

`app/routing/nearest_node.py`'s `InMemoryNearestNodeLocator`: a linear
scan computing `app.roads.geo_utils.haversine_distance_meters` (the same
real geodesic calculation used throughout this codebase, never a raw
lat/lon comparison) to every candidate node, keeping the closest — O(n)
per lookup, acceptable at prototype scale (the same tradeoff already
documented for Milestone 6B's bounding-box pre-filter). **Never
fabricates a match**: if the nearest node is farther than
`ROUTING_MAX_SNAP_DISTANCE_METERS`, or the graph has no nodes at all,
`find_nearest()` returns `None` and routing reports `found=False`. A
future KD-tree or PostGIS-backed implementation (`<->` nearest-neighbor
operator) would satisfy the same `NearestNodeLocator` Protocol.

Coordinate validation reuses `app.roads.schemas.GeographicCoordinate`
(factored out of `RoadNode` specifically for this reuse) — the exact
same latitude/longitude range/finiteness validation `RoadNode` itself
uses. There is no separate CRS field to validate: `GeographicCoordinate`
only ever means WGS84, so there is exactly one interpretation of its two
numbers to get wrong, and Pydantic already rejects that at the schema
boundary.

### Route schema

`RouteResult` (`app/routing/schemas.py`) — `found=False` is a
**structured result, not a missing/empty one**: every list field stays
`[]`, every optional scalar stays `None`, and `reason` explains why (no
path exists, no road network is loaded, no node was found near the
requested coordinates, no risk data for `risk_aware`, ...). Never
silently returns an empty *successful* route.

`edge_sequence` reuses `app.roads.schemas.RoadEdge` directly — no second,
parallel edge type, so a route's segments carry the exact same
`base_cost`/`risk_score`/`risk_level`/`accessibility` fields already
established. `accumulated_risk` is `None` (not `0.0`) when risk was never
assessed for the route at all (e.g. `distance_only` without an available
risk analysis) — distinct from `0.0`, which means risk *was* assessed and
genuinely found nothing nearby (the same `None`-vs-`0.0` distinction
`RoadEdge.risk_score` itself already makes).

"Estimated travel cost/time" (mentioned as optional — "if supported" — in
the milestone's own output spec) is **not implemented**: `RoadEdge.maxspeed`
is a raw, unit-inconsistent OSM string (Milestone 6A deliberately never
parses or unit-converts it), and fabricating a travel-time estimate from
it would violate this project's "never fabricate" principle running
through every prior milestone.

### API

`POST /api/v1/routing` — see the endpoint reference above for the full
request/response shape. `RoutingRequest.mode` has **no default** (unlike
most optional fields elsewhere in this API): `distance_only` and
`risk_aware` produce meaningfully different results, so a caller must say
which one it wants.

`RoutingService.route()` calls `RoadRiskService.get_road_risk()`
**unconditionally**, for both modes — not just `risk_aware`. This is
deliberate: whenever risk data *is* available, `distance_only` routing
still reports how risky its (risk-blind) chosen path turned out to be,
which is exactly what "shortest path is riskier" scenarios and route
comparison need. When risk data *isn't* available (the honest, common
state today, since no real georeferencing pipeline exists yet — see
"Road risk model," above), `distance_only` still works, falling back to
the road network's raw (non-risk-assessed) edges; only `risk_aware` mode
actually requires risk data to proceed.

### Route comparison methodology

`RoutingService.compare_routes()` (not exposed as a separate HTTP
endpoint this milestone — a service-level capability, matching this
project's established "minimal API surface" discipline) runs both modes
for the same start/destination/analysis and returns a `RouteComparison`
(`app/routing/schemas.py`):

- **Distance/risk/cost of each** — the two full `RouteResult`s, so every
  number is traceable back to real edges, not just a diff.
- **`distance_difference`** — `risk_aware.total_distance -
  distance_only.total_distance` (meters; `>= 0` whenever both routes are
  found, since `distance_only` is, by construction, the minimum-distance
  route among traversable edges).
- **`risk_difference`** — `risk_aware.accumulated_risk -
  distance_only.accumulated_risk` (typically `<= 0`: the point of
  `risk_aware` is to reduce accumulated risk).
- **`routes_differ`** — whether the two node sequences differ at all.
- **`detour_ratio`** — see "Research metrics," below.

Every field here is purely descriptive — nothing in `RouteComparison`
feeds back into route selection.

### Research metrics

`app/routing/metrics.py`, purely derived from already-computed routes:

1. **Route distance** — `RouteResult.total_distance`.
2. **Route risk** — `RouteResult.accumulated_risk`.
3. **Routing cost** — `RouteResult.total_cost`.
4. **Number of risky segments** — `count_risky_segments()`: edges at
   `RiskLevel.HIGH`/`.CRITICAL` actually included in a route.
5. **Number of blocked segments avoided** — `count_blocked_edges()`:
   `blocked` edges present in the graph a route was searched over. Every
   one of them was, by construction, excluded from the search (see
   "Accessibility behavior") — this reports how many existed to be
   avoided, **not** a claim about a specific counterfactual detour
   distance (computing that would need a second, blockage-ignoring
   search, which this milestone doesn't run).
6. **Detour ratio** — `detour_ratio() = risk_aware_distance /
   distance_only_distance`, exactly the specified formula. `None` (never
   a fabricated ratio) if either distance is unavailable or the baseline
   distance is zero.

`high_risk_edges_avoided()` additionally lists the specific `"source->target"`
edges `distance_only` used at `HIGH`/`CRITICAL` risk that `risk_aware`
did not — see "Explainability," below. **No safety claim is made beyond
what the actual computed risk values show** — a lower `accumulated_risk`
under this project's own baseline heuristic risk model, nothing more.

### Research experiment (controlled algorithmic demonstration)

`test_risk_aware_prefers_the_longer_safer_path_research_benchmark` in
`tests/test_routing.py` — **not a real-world emergency claim**, a
deterministic, synthetic demonstration that the mode switch actually
changes routing behavior as designed:

```
Route A: shorter (150m), higher risk (risk_score=1.0 throughout)
Route B: longer (300m), lower risk (risk_score=0.0 throughout)
```

`distance_only` chooses Route A (it only ever looks at distance);
`risk_aware`, with the default configured risk penalty, chooses Route B
instead (`50m x 5 x 3 = 750` > `300m`) — verified by direct assertion on
the resulting node sequences.

### Explainability

`RouteResult`/`RouteComparison` expose enough to answer "why was this
route selected?" without an LLM (explicitly not implemented this
milestone — see "Do not implement"):

- **High-risk edges avoided** — `RouteComparison.high_risk_edges_avoided`.
- **Blocked edges avoided** — every edge in `edge_sequence` has
  `accessibility`; `AccessibilitySummary.blocked` on a found route is
  always `0`, and `RouteComparison.blocked_segments_in_graph` reports how
  many existed in the graph as a whole.
- **Additional distance accepted** — `RouteComparison.distance_difference`.
- **Risk reduction obtained** — `RouteComparison.risk_difference`
  (negative = risk went down).

### GeoJSON route output

`app/routing/geojson.py`'s `route_to_feature()` converts a `RouteResult`
into a standard GeoJSON (RFC 7946) `Feature` with a `LineString`
geometry — reuses `app.ml.geospatial.geometry.Coordinate` (the shared
`(x, y)` tuple type every geometry module in this codebase already uses),
**not** `app.ml.geospatial.geojson.Feature`/`FeatureCollection` directly,
since those are typed specifically for building predictions
(`building_id`/`damage_class`/... properties that make no sense for a
route) — this module defines its own, structurally identical `Feature`
following the exact same RFC 7946 pattern, with the properties this
milestone actually needs (`routing_mode`/`total_distance`/`total_cost`/
`accumulated_risk`). `None` if the route wasn't found, or has fewer than
2 points (a `LineString` requires at least 2 positions — the trivial
start==destination route has only 1) — never a fabricated geometry.

### Performance

Dijkstra/A* over an adjacency structure built once per request
(`GraphView`, O(nodes + edges)); nearest-node lookup is O(n) per
coordinate. No distributed systems, Redis, Celery, GPU routing, or
external routing API — none of that is warranted at the prototype road
graph sizes this milestone targets, and adding it now would be
unjustified infrastructure for a problem that doesn't exist yet.

### Do not implement (this milestone)

LLM summaries, hazard prediction, tsunami prediction, flood forecasting,
a 3D frontend, live navigation, traffic prediction, or real-time vehicle
tracking. Route *optimization* beyond the two modes described above (no
multi-stop routing, no alternate-route ranking) is also out of scope.
All later milestones.

## AI incident intelligence (Milestone 7)

```
API -> IncidentIntelligenceService -> Context Builder -> LLM Provider
    -> Schema Validation -> Incident Briefing
```

Converts SentinelAI's already-computed, deterministic results (damage —
Milestones 3/5, road risk — Milestone 6B, routing — Milestone 6C) into a
short, structured operational summary for a rescue coordinator.
Implemented in `app/incident/` (the pipeline itself) plus
`app/services/incident_intelligence_service.py` (DI-facing orchestration,
matching every other `*Service` in this codebase).

### Why an LLM is used

Turning a page of counts, ratios, and edge lists into a readable sentence
is a genuine language task — exactly what an LLM is good at, and tedious
to hand-write as string templates for every possible combination of
available/unavailable data. This is a **communication and synthesis
layer only**.

### Why the LLM is not the decision-maker

Every decision this milestone specifies as off-limits to the LLM
(damage classification, coordinates, road risk, route selection, hazard
prediction) is already made by earlier milestones before the LLM is ever
invoked. This is enforced **structurally**, not by instruction alone:

- `LLMNarrativeOutput` (`app/incident/schemas.py`) — the *only* type an
  `LLMProvider` is trusted to produce — has exactly four free-text
  fields (`priority_area`, `route_summary`, `key_findings`,
  `limitations`). It has no `incident_severity`/`confidence`/
  `affected_structures` fields at all, so there is nothing for a
  misbehaving provider to fabricate there even if it tried — Pydantic's
  `model_validate` simply ignores unrecognized keys.
- `IncidentBriefing.incident_severity`/`.confidence`/`.affected_structures`
  are always computed by `app.incident.severity`, directly from
  `IncidentContext`'s real numbers (`app.incident.briefing_builder`),
  never read from the narrative.
- `IncidentContext` (the *only* input an LLM ever sees) is itself built
  entirely from already-computed Milestone 3/5/6B/6C output
  (`app.incident.context_builder`) — no new analysis, no re-derivation,
  and structurally no way for the LLM to be asked to *decide* anything.

### Context schema

`IncidentContext` (`app/incident/schemas.py`), built by
`build_incident_context()`:

- **`damage`** (`DamageContext`) — `total_buildings`/`damaged_buildings`/
  `severely_damaged`/`destroyed` (reused `DamageSummary`, Milestone 3),
  mean `BuildingDamage.confidence`, up to `INCIDENT_MAX_LISTED_STRUCTURE_IDS`
  high-priority structure IDs (reused `is_high_priority()`, Milestone 5),
  and a bounding box over georeferenced buildings only (reused
  `BoundingBoxGeometry`/`representative_point()`, Milestone 5).
- **`road_risk`** (`RoadRiskContext`) — edge counts by risk level and
  accessibility, the highest risk level seen, and a sample of
  contributing building IDs (from Milestone 6B's `RoadEdge.risk_sources`).
- **`route`** (`RouteContext`) — `selected_*` (the `risk_aware` route)
  vs. `baseline_*` (`distance_only`), detour ratio, and avoided high-risk
  segment count — a direct mapping of Milestone 6C's `RouteComparison`.

Every sub-context has `available: bool` + `reason: str | None`; when
`available=False`, every other field stays at its empty default — never
a fabricated value. `route` is only populated if the caller explicitly
requests it (`POST .../summary` with a `route` body) — this package has
no way to invent a start/destination.

### Incident briefing schema

`IncidentBriefing` (`app/incident/schemas.py`) — the response of both
`GET`/`POST /api/v1/analysis/{analysis_id}/summary`: `incident_severity`,
`affected_structures`, `priority_area`, `route_summary`, `key_findings`,
`limitations`, `confidence`, `generated_at`, `source`
(`"provider"`/`"fallback"`), `prompt_version`, and a fixed `disclaimer`
(see "Safety controls," below).

### LLM provider abstraction

`LLMProvider` (`app/incident/provider.py`) is a `Protocol` with one
method, `generate_incident_summary(context) -> str` — the same
structural, duck-typed DI seam this codebase already uses for
`DamageModel`/`BuildingLocalizer`/`RoadNetworkSource`. Nothing in
`IncidentIntelligenceService` or the API layer imports a concrete
provider; `app/api/deps.py`'s `get_llm_provider()` is the only place that
branches on `Settings.LLM_PROVIDER` (`"deterministic"` | `"mock"` |
`"anthropic"`):

| Provider | File | Network/API key |
|---|---|---|
| `DeterministicSummaryProvider` (default) | `app/incident/fallback.py` | None — pure template |
| `MockLLMProvider` | `app/incident/mock_provider.py` | None — test-only, configurable failure modes |
| `AnthropicLLMProvider` | `app/incident/anthropic_provider.py` | Real Anthropic API call |

Adding OpenAI or a local Hugging Face model is a new file implementing
`generate_incident_summary()` plus one new branch in `get_llm_provider()`
— no change anywhere else.

### Prompt design

`PROMPT_VERSION = "incident_summary_v1"` (`app/incident/prompt.py`),
stamped onto every `IncidentBriefing` so a future evaluation can compare
results across prompt changes. `SYSTEM_PROMPT` instructs the model to:
summarize damage, identify the priority area, explain route selection,
summarize road risk, call out uncertainty, list minimum limitations, and
— critically — **never** state casualties, injuries, deaths, exact
coordinates, official road closures, weather, emergency instructions,
evacuation orders, or hazard timing, using "Information unavailable."
instead. Output must be exactly the four `LLMNarrativeOutput` fields as a
single JSON object, no prose outside it.

### Structured grounding / prompt injection defense

`IncidentContext` deliberately contains **no free text a user
controls** — no filenames, no arbitrary uploaded strings — the safest
defense against prompt injection is to never place untrusted text where
a model might treat it as instructions. `build_user_message()`
additionally wraps the context in explicit `<incident_context>...
</incident_context>` delimiters with an instruction that the block is
DATA, never instructions — defense in depth on top of the structural
exclusion.

### Hallucination controls

Four independent layers, each imperfect alone:

1. **Prompt instructions** (above) — a request, not a guarantee.
2. **Structural exclusion** of untrusted free text from the context.
3. **`app.incident.grounding.filter_unsupported_claims()`** — a
   keyword/pattern filter (not semantic understanding) run on every
   narrative regardless of how well the model followed its prompt.
   Rejects any of the four free-text fields containing a banned topic
   (casualties/deaths/injuries, tsunami, flood, evacuation, weather,
   road closures) or an invented-looking coordinate (4+ decimal places
   — `IncidentContext` never gives the model raw lat/lon to legitimately
   quote). Deliberately allows "blocked"/"restricted" through — this
   system's own grounded `AccessibilityStatus` vocabulary, not an
   invented claim. Rejection discards the *entire* narrative (never
   tries to surgically edit prose) and falls through to the fallback.
4. **Deterministic fallback** (below) — the backstop that can only ever
   state what's really in the context.

### Deterministic fallback

`build_fallback_narrative()` (`app/incident/fallback.py`) is a pure,
template-based function of `IncidentContext` — no LLM, no network. Used
in two ways: as the actual configured provider
(`DeterministicSummaryProvider`, `Settings.LLM_PROVIDER` default) so
SentinelAI works fully offline with zero configuration, *and* as the
automatic fallback whenever another provider fails, times out, returns
malformed JSON, or fails the grounding filter
(`IncidentIntelligenceService._get_narrative()`: generate -> parse ->
ground -> assemble, falling back at any failed stage). `source` on the
response distinguishes which happened — the briefing shape is identical
either way, so a caller never sees a 500 or a partial result because an
LLM was unavailable.

### Confidence and uncertainty

`ConfidenceLevel` (`classify_confidence()`, `app/incident/severity.py`)
is a threshold on the mean of real `BuildingDamage.confidence` values —
never an LLM's self-reported confidence, and never conflated with
`IncidentSeverity` (also computed independently, from
destroyed/severely-damaged ratios). Both are explicitly documented as
**engineering categories, not a validated emergency-management scale** —
the same honesty this codebase already applies to `RiskLevel`
(Milestone 6B) and `DamagePriority` (Milestone 5).

### Safety controls

Every `IncidentBriefing.disclaimer` is a fixed string, always set
server-side (`app/incident/briefing_builder.py`), never LLM-generated:
AI output is advisory; damage predictions may be wrong; road risk is
modeled, not verified; road accessibility may be unverified; real
emergency decisions require authoritative information. On the
`"fallback"` path, `limitations` always includes a fixed minimum set
(`_STANDARD_LIMITATIONS`, `app/incident/fallback.py`). On the
`"provider"` path, `limitations` is whatever the provider returned — the
prompt instructs it to include the same minimum set, but this is not
currently structurally enforced (see "Limitations" in the final report
for this milestone). The disclaimer itself, however, is always present
either way, since it is never sourced from the narrative at all.

### API

`GET`/`POST /api/v1/analysis/{analysis_id}/summary` — see the endpoint
reference above. Both delegate entirely to
`IncidentIntelligenceService.get_summary()`; no business logic in the
route (`app/api/v1/endpoints/analysis.py`). `POST` exists only to accept
an optional `route` body — never introduced as an unnecessary second
endpoint for identical behavior.

### Tests

`tests/test_incident.py` — deterministic, no network, no API key, no
GPU: context construction (full data, empty damage, missing route,
missing road-risk), the `LLMProvider` interface, every `MockLLMProvider`
behavior (valid/malformed/timeout/error/unsupported-claim),
`parse_llm_output()` on valid/malformed/fenced JSON,
`IncidentIntelligenceService`'s fallback behavior on every failure mode,
the deterministic fallback (including a regression test that its own
output survives its own grounding filter), the grounding filter's
banned-claim and allowed-vocabulary cases, confidence-level thresholds,
the summary API (200/404/422, GET and POST), Pydantic schema validation,
and a small deterministic evaluation fixture (below).

### Future evaluation methodology (not implemented)

Documented, not measured, this milestone: factual consistency (does the
narrative's text match `IncidentContext`'s numbers exactly, beyond the
keyword-level grounding filter), unsupported-claim rate at scale (this
milestone tests specific known cases, not a statistical rate over many
generations), completeness (did the narrative address every section the
prompt asked for), latency and token usage (only relevant once a real
provider is used routinely), and human usefulness (requires actual
rescue-coordinator evaluation, out of scope for an automated test
suite). `tests/test_incident.py`'s evaluation fixture is a small,
deterministic sanity check — asserting a known context produces the
facts it supports — not a claim that any of the above is measured.

### Do not implement (this milestone)

Hazard prediction, tsunami prediction, flood forecasting, evacuation
recommendation, autonomous emergency decisions, live emergency alerts, a
frontend, or 3D visualization.

## ML architecture (Milestones 3A and 3C)

**No model has been trained. Nothing in this codebase fabricates a
prediction.** `POST /api/v1/analysis` still only ingests and stores an
image (Milestone 2, unchanged). This section covers the inference
architecture (3A) and its first concrete, CPU-compatible adapters (3C):

```
Image -> [Stage 1: BuildingLocalizer] -> crop each located building
      -> [Stage 2: TorchDamageClassifier] -> RawDetection
      -> Postprocessor -> DamageAnalysis
```

Both stages compose into the *same, unmodified* `DamageModel` Protocol
from 3A via `TwoStageDamageModel` — nothing downstream (`inference.py`,
the DI seam, a future route) needs to know two stages exist. Implemented
in `app/ml/` — a package with **no FastAPI import anywhere in it**:

| File | Role |
|---|---|
| `schemas.py` | `DamageClass`, `BuildingDamage`, `DamageSummary`, `DamageAnalysis`, `ModelStatus` — the typed result contracts. |
| `spatial.py` | `BoundingBox` (pixel-space, with `.iou()`) — the spatial primitive both stages share. |
| `localizer.py` | **Stage 1.** `BuildingLocalizer` Protocol + `LocalizedBuilding`. Only implementation: `UnavailableBuildingLocalizer` — see "Why Stage 1 has no real implementation yet," below. |
| `classifier.py` | **Stage 2.** `TorchDamageClassifier` — a ResNet18 + 4-class head, the first concrete, real (if untrained) model adapter. See "Selected baseline model." |
| `pipeline.py` | `TwoStageDamageModel` — composes Stage 1 + Stage 2 into `DamageModel`. |
| `model.py` | The `DamageModel` Protocol (`load()` / `predict()` / `health()`), `RawDetection`, `ModelNotAvailableError`. Also `UnavailableDamageModel`, the original single-model stub from 3A — no longer wired into `deps.py`, kept as the simplest possible `DamageModel` implementation and still directly tested. |
| `preprocessing.py` | `load_image()`, `to_rgb()`, `ImagePreprocessor` (resize + RGB-normalize). Stops at a `PIL.Image` — model-specific normalization is applied by whichever adapter needs it (see `classifier.py`'s ImageNet statistics). |
| `postprocessing.py` | `build_analysis()` / `summarize_buildings()` — reshapes a model's raw detections into `BuildingDamage`/`DamageSummary`/`DamageAnalysis`. Invents nothing, including spatial data: `bounding_box` is only ever copied through from what the model produced. |
| `inference.py` | `DamageInferenceEngine` — orchestrates preprocessing → model → postprocessing for a whole request. |
| `evaluation.py` | `evaluate_classification()` — precision/recall/F1/macro-F1/confusion matrix. See "Evaluation methodology," below. |

### Selected baseline model

**ResNet18 (`torchvision.models.resnet18`), final layer replaced with a
4-class linear head, via `app/ml/classifier.py`'s `TorchDamageClassifier`.**
This is the outcome of the model-selection analysis conducted for
Milestone 3C, comparing object detection, instance segmentation, semantic
segmentation, image classification, and a full two-stage system against
this project's actual constraints (CPU-only, ~2 weeks, xBD's ground-truth
polygon annotations, and the existing `RawDetection`/`BuildingDamage`
contract). A pretrained-CNN classifier had the best CPU training *and*
inference profile, the lowest implementation risk, and matches the
classification half of the published xView2 challenge baseline — not an
invented shortcut. **This is not a claim of state-of-the-art performance**
— it's a deliberately modest, fast-to-validate baseline; see "Known
limitations," below.

### Why this task formulation

Stage 2 (`TorchDamageClassifier`) classifies a single *already-located*
building crop — it does not find buildings itself. That's Stage 1's job,
kept as a genuinely separate, swappable component
(`BuildingLocalizer`/`UnavailableBuildingLocalizer`, `app/ml/localizer.py`).
Isolating classification from localization means the hardest, most novel
part of the problem (damage-severity estimation) can be validated on its
own — via xBD's ground-truth polygons standing in for "known building
locations" during development/evaluation — without also solving building
localization from scratch in the same two weeks.

### Why Stage 1 has no real implementation yet

No off-the-shelf pretrained detector or segmentation model applies here:
torchvision's standard model zoo is trained on COCO or Pascal VOC, and
**neither has a "building" class**. There is no honest way to produce a
real building location from a generic pretrained model — only from a model
trained specifically for it, or from an external source (a separate
detector, or building-footprint data such as OpenStreetMap). Rather than
wrap a COCO detector and imply it finds buildings, `UnavailableBuildingLocalizer`
reports `model_loaded=False` and `locate()` raises `LocalizerNotAvailableError`
— the same honesty contract Stage 2 provides when no checkpoint exists.
`TwoStageDamageModel.predict()` normalizes both stages' failures to
`ModelNotAvailableError`, so any caller only needs to handle one exception
type regardless of which stage is missing. **This is still exactly true
for `Settings.MODEL_PROVIDER="legacy_resnet"`** (the pre-F4 architecture,
preserved unmodified as an option — see below for why it isn't the
default anymore).

## Milestone F4 — real inference

Milestones 3A/3C above built the inference *architecture*; nothing in
them ever produced a genuine prediction (Stage 1 had no implementation
at all, and Stage 2 required an external fine-tuned checkpoint that was
never trained). Milestone F4 makes `POST /api/v1/analysis` perform
**real, working, CPU-only inference by default** — no training, no
fine-tuning, no GPU, no fabricated/hardcoded/random output — by
replacing both stages with implementations that don't need a checkpoint
that doesn't exist:

```
Image -> [Stage 1: TileRegionLocalizer] -> crop each tile
      -> [Stage 2: ClipZeroShotDamageClassifier] -> RawDetection
      -> Postprocessor -> DamageAnalysis -> BuildingDamage -> SpatialRepository
      -> (Milestone F3, unmodified) analysis_adapter -> search zones -> recommendations
```

### Model selection

| | |
|---|---|
| **Model** | CLIP, architecture `ViT-B-32` |
| **Version / pretrained tag** | `openai` (OpenAI's original published CLIP checkpoint, served via the Hugging Face Hub / `timm`) |
| **Provider / library** | [`open_clip`](https://github.com/mlfoundations/open_clip) (`open_clip_torch` on PyPI) |
| **Task used for** | Zero-shot damage-severity classification (Stage 2) — no object detection, no segmentation |
| **Device** | CPU (`Settings.MODEL_DEVICE="cpu"`, the default; no CUDA anywhere in this codebase) |
| **xBD-trained?** | **No.** This is a general-purpose pretrained vision-language model. It was never trained or fine-tuned on xBD, xView2, or any disaster-specific dataset. |
| **License** | CLIP's original weights are released by OpenAI under the MIT license; `open_clip` itself is MIT-licensed. |

**Why this model:** it is the only realistic way to get *real, working*
inference out of a CPU-only, no-training, no-GPU milestone. Every
alternative considered required either training data this repository
doesn't have (a fine-tuned classifier — the original Milestone 3C plan,
still fully implemented and available via `MODEL_PROVIDER="legacy_resnet"`,
just never trained) or a pretrained model whose training classes don't
include "building" (any standard COCO/Pascal-VOC detector — see "Why
Stage 1 has no real implementation yet," above, for why that's still
true). CLIP's zero-shot classification is a genuinely real, well-
established technique (not a hack invented for this milestone): a real
forward pass produces a real image embedding, compared via real cosine
similarity against four real text-prompt embeddings
(`app/ml/clip_classifier.py`'s `_DAMAGE_PROMPTS`), soft-maxed into a
`RawDetection`. **No accuracy/precision/recall/F1/mAP/IoU claim is made
anywhere in this codebase for this model** — none has been measured,
and none should be assumed.

### Confidence interpretation (F4 — read before using `confidence`)

Exactly the same discipline "Confidence interpretation" (above)
established for the legacy classifier, restated because it matters even
more here: `RawDetection.confidence` is CLIP's own raw softmax
probability over the 4 candidate prompts — genuine model output, never
assigned manually — and it is **not a calibrated probability**. CLIP was
never calibrated (or even trained) for damage-severity classification
specifically, so a value of 0.9 does not mean "90% likely correct."
Nothing converts this raw score into a fabricated percentage anywhere
downstream — F3's `analysis_adapter.py` deliberately keeps
`Uncertainty.confidence=None` throughout and only ever derives a
qualitative `low`/`moderate`/`high` band from it (see
`docs/architecture/intelligence.md`).

### Why Stage 1 is deterministic tiling, not a "real" localizer

Per "Why Stage 1 has no real implementation yet" above, no legitimate
pretrained model detects buildings. Rather than wrap an unrelated
detector and imply it does, `app/ml/tile_localizer.py::TileRegionLocalizer`
deterministically partitions the image into a `Settings.MODEL_TILE_GRID`
x `MODEL_TILE_GRID` grid (default `2` -> 4 tiles) of real, correctly-
computed pixel regions — **not** a machine-learning model, and **not** a
claim that each tile is a verified individual building. Every
`BuildingDamage` produced this way genuinely represents "damage
classification for this image region," which is what this milestone
can honestly deliver; a real per-building detector remains a documented
future extension (see "Recommended F5" in the Milestone F4 final
report, or `docs/architecture/ai-engine.md`).

### Model lifecycle (Milestone F4)

`app/api/deps.py::get_building_localizer`/`get_damage_classifier` are
each backed by a small, module-level, config-keyed cache (`_localizer_cache`/
`_classifier_cache`) — a real model is downloaded/loaded **at most once
per distinct configuration**, never once per request, the same
"module-level singleton" pattern every in-memory repository in this
codebase already uses (just parametrized by config instead of
unconditional). A load failure (e.g. no network on a cold cache) is
caught internally and turned into a `_LoadFailedClassifier` stand-in —
it never crashes the *upload* request itself (which resolves the whole
DI tree, including the model, before `POST /api/v1/analysis` even
returns `201`); the failure only surfaces once background processing
actually invokes the model, as an honest `MODEL_LOAD_FAILURE`.
`GET /api/v1/model/status` (see `docs/api/endpoints.md`) reports
`enabled`/`provider`/the real `ModelStatus` without triggering a load of
its own — it reads whatever the existing DI wiring already
constructed.

### CPU limitations

This entire pipeline runs on CPU (`torch.cuda.is_available()` is `False`
on the development machine, and nothing in this codebase requires it not
to be). What CPU-only actually constrains:

- **Training** a real classifier to convergence is realistically a
  multi-hour-to-multi-day undertaking on CPU even for a small subset —
  see "Training vs. inference," below, for why this happens externally.
- **Inference** (a single crop through `TorchDamageClassifier.classify()`)
  is fast on CPU — well under a second per crop for a ResNet18 at 224×224 —
  confirmed by this milestone's own tests running the full forward pass
  with no GPU.
- Model size, input resolution, and batch size are all kept modest by
  design (ResNet18 rather than a larger backbone; 224×224 crops) because
  larger choices cost real CPU minutes, not GPU seconds.

### Training vs. inference

No training happens in this codebase or this milestone. What a real,
usable checkpoint requires:

1. **Model family:** the same architecture `build_resnet_classifier()`
   constructs (`resnet18` + a 4-class `Linear` head) — an external training
   script should import this exact function so the trained weights are
   guaranteed to fit the inference-time architecture.
2. **Pretrained weights:** ImageNet-pretrained ResNet18 weights
   (`torchvision.models.ResNet18_Weights.DEFAULT`) as the starting point for
   transfer learning — fetched during the *external* training run, never by
   this repository's shipped code (see below).
3. **Training data:** a small, disaster-level-split subset of xBD (2–4
   disasters), loaded via the existing `app.ml.datasets.xbd.XbdDataset` —
   see "xBD usage," below, and `datasets/README.md` for where to place it.
4. **Training configuration:** weighted cross-entropy (or minority-class
   oversampling) to counter xBD's class imbalance toward `no_damage`,
   ImageNet mean/std normalization (`classifier.py`'s `_IMAGENET_MEAN`/
   `_IMAGENET_STD`), 224×224 crops, a small epoch count with early stopping
   on validation macro-F1.
5. **Where to train:** externally, on GPU-available compute (a cloud
   instance, Colab, or similar) — not this development machine. The
   resulting checkpoint (`model.state_dict()`) is saved as a `.pt` file
   and brought back locally, then referenced via `Settings.MODEL_PATH` for
   CPU-only inference. This is the only way a checkpoint reaches this
   codebase; **`TorchDamageClassifier` never downloads anything** —
   `build_resnet_classifier()` always constructs with `weights=None`, and
   `load()` only ever reads a local file. Even the ImageNet-pretrained
   starting point in step 2 is fetched during that external run, not here.

### xBD usage

Reuses `app.ml.datasets.xbd.XbdDataset` and `app.ml.datasets.schemas`
entirely — no dataset parsing is duplicated (see Milestone 3B, above).
`TorchDamageClassifier` and `TwoStageDamageModel` operate on `PIL.Image`
crops and know nothing about xBD directly; an (not-yet-written) training
script is what would bridge `DatasetSample`/`BuildingAnnotation` into
crops + labels for training, and `evaluate_classification()` (below) into
scoring. Post-disaster imagery only, for the reasons already documented
under "Pre/post-disaster comparison" (Milestone 3B, above) — unchanged by
3C.

### Prediction schema

`RawDetection` (`app/ml/model.py`) and `BuildingDamage`
(`app/ml/schemas.py`) each gained one new, optional field:
`bounding_box: BoundingBox | None = None` (`app/ml/spatial.py`) — the
smallest backwards-compatible extension that lets a real building location
flow from Stage 1 through to the API-facing schema without another schema
change later. `TwoStageDamageModel` populates it from whatever Stage 1
located; `TorchDamageClassifier` alone never sets it (it doesn't locate
anything). **No coordinates are ever invented** — the field is `None`
unless a real localizer produced a real box. Existing fields
(`building_id`, `damage_class`, `confidence`) are unchanged.

### Confidence interpretation

`TorchDamageClassifier.classify()`'s confidence is the model's own softmax
probability for its predicted class (`torch.softmax(logits, dim=1)`) —
never a manually assigned value. **This is not a calibrated probability.**
A softmax output of 0.9 does not mean "90% likely to be correct" unless
the model has been explicitly calibrated (e.g. temperature scaling against
a held-out set) — which it has not been, and which is not implemented in
this milestone. Treat confidence as a relative ranking signal between
predictions from the same model, not as a probability in the statistical
sense.

### Evaluation methodology

`app.ml.evaluation.evaluate_classification()` computes per-class
precision/recall/F1, macro-F1 (the headline metric — it weights all four
classes equally rather than being dominated by `no_damage`), and a
confusion matrix, from two index-aligned lists (predictions and ground
truth for the same buildings, in the same order — matching this
milestone's "known building locations" scope). It refuses to compute
anything on empty input (`EvaluationNotPerformedError`) rather than
reporting misleading zeros. `BoundingBox.iou()` (`app/ml/spatial.py`) is
available for detection-quality evaluation once Stage 1 produces real
locations — not exercised yet, since there's nothing real to measure.
**No trained model or evaluation dataset exists, so no evaluation has been
performed** — nothing in this codebase currently calls this module with
real predictions.

### Known limitations

- **As of Milestone F4, real inference happens by default** — but Stage 1
  is deterministic tiling, not a real per-building detector (no
  legitimate one exists — see above), and Stage 2 is a general-purpose,
  zero-shot CLIP classifier, **not** fine-tuned or trained on xBD or any
  disaster-specific dataset. Treat predictions as a coarse, honestly-
  uncalibrated signal — see "Confidence interpretation (F4)," above —
  never a validated damage assessment.
- **The original Milestone 3A/3C fine-tuned-checkpoint architecture
  still exists and is fully preserved** (`MODEL_PROVIDER="legacy_resnet"`)
  but remains untrained — no checkpoint has ever been produced for it.
- **No pre/post-disaster comparison** — post-disaster image only (a
  documented Milestone 3A/3B decision, unchanged).
- **No geospatial (latitude/longitude) output** — `BoundingBox` is pixel-space
  only; see "Geospatial future support," below. Every F4 prediction is
  therefore `georeferenced=False`/`coordinate_reference_system=IMAGE` —
  F3's intelligence pipeline honestly reports `NO_GEOREFERENCE` for a
  real, uploaded image unless a caller separately supplies georeferencing
  (see `tests/test_ml_real_inference_integration.py`).
- **This system does not predict, and cannot currently be used to predict,
  tsunamis, earthquakes, floods, or any other hazard** — its only intended
  eventual capability is post-hoc building damage severity from imagery of
  a disaster that has already occurred.
- **No accuracy/precision/recall/F1/mAP/IoU has been measured for the
  CLIP zero-shot path** — `evaluate_classification()` remains available
  (see "Evaluation methodology," above) for whenever ground-truth
  damage-severity labels exist to measure against.

### Geospatial future support

`BoundingBox` (pixel-space) is the schema seam for this, not an
implementation of it. The intended path, none of which is implemented in
this milestone: a real Stage 1 localizer produces pixel boxes ->
georeferencing metadata (xBD's label JSON separately provides geographic
`features.lng_lat` geometries alongside the pixel-space `features.xy` this
codebase currently reads — see `app/ml/datasets/xbd.py`) converts pixel
coordinates to latitude/longitude -> stored in PostGIS -> joined against a
road network -> a routing algorithm. Routing itself is explicitly out of
scope for this milestone.

### Why predictions are never fabricated

SentinelAI's output informs real disaster-response decisions. A
plausible-looking but fake damage assessment is worse than an honest "no
model available" — it risks misdirecting rescue resources. Every
component that can genuinely fail (`UnavailableBuildingLocalizer`,
`TorchDamageClassifier` with no checkpoint, `UnavailableDamageModel`,
`ClipZeroShotDamageClassifier` before `load()` succeeds) fails loudly
rather than returning a placeholder result, and every
`ModelStatus.model_loaded` is computed from real state, never hardcoded
`True`. As of Milestone F4, when a prediction *is* produced, it is a
genuine forward pass through real pretrained weights — never a random
number, a lookup table, or a value chosen to "look right" (see "Model
selection," above).

### Research integrity: five distinct things, not one

This codebase distinguishes, and this document uses the terms
deliberately:

1. **Model infrastructure** — the `DamageModel`/`BuildingLocalizer`
   Protocols, `TwoStageDamageModel`, preprocessing/postprocessing. Exists
   today, fully tested.
2. **A pretrained model** — as of Milestone F4, genuinely loaded and used
   by default: CLIP `ViT-B-32`/`openai`, real weights, real inference,
   zero training required (see "Milestone F4 — real inference," above).
   The legacy path's ImageNet weights for the ResNet18 backbone are a
   separate case — not currently loaded by any shipped code path (see
   "Training vs. inference"), used only as an external training starting
   point for that (still-untrained) architecture.
3. **A fine-tuned/xBD-trained model** — a checkpoint actually trained on
   xBD. **Does not exist**, for either architecture.
   `Settings.MODEL_PATH` is unset by default and nothing in this
   repository provides one. The CLIP path (Milestone F4's default) does
   not need one — it performs zero-shot classification instead — but it
   is, for exactly that reason, also not xBD-trained.
4. **A calibrated model** — one whose confidence scores are validated
   against measured accuracy. **Does not exist** for either architecture
   — see "Confidence interpretation (F4)," above.
5. **An evaluated model** — a model with measured metrics via
   `evaluate_classification()`. **Does not exist**, since no ground-truth
   damage-severity ranking has ever been run against either model's
   output.

Nothing in this codebase represents an untrained, uncalibrated, or
unevaluated model as more validated than it actually is.

## Dataset pipeline (Milestone 3B)

**No dataset is downloaded, bundled, or committed by this codebase.** This
milestone prepares the code to *read* a dataset the user places on disk
themselves — parsing, validation, and typed sample/annotation structures —
not a trained model or any model-specific preprocessing.

```
Dataset -> Image -> Building annotation -> Damage label -> (future: model training -> evaluation)
```

Implemented in `app/ml/datasets/` — inside `app/ml/` (the same "no FastAPI
import" package Milestone 3A established) rather than a new top-level
package, since it needs nothing beyond what `apps/api` already depends on
(Pillow, Pydantic). If training later needs heavy, training-only
dependencies (PyTorch, an augmentation library, ...) that shouldn't bloat
the deployed API's dependency tree, this is the natural extraction point
into `packages/ai/` — deferred until that's an actual, not speculative,
need.

| File | Role |
|---|---|
| `schemas.py` | `ImageSample`, `BuildingAnnotation`, `DatasetSample`, `DatasetSplit` — what's on disk, as typed structures. Reuses `app.ml.schemas.DamageClass`: the taxonomy a dataset's labels are normalized into is exactly what a trained model will predict — one definition, not two. |
| `base.py` | The `DisasterDamageDataset` Protocol (`root` / `list_samples` / `load_image_sample` / `load_annotations`) — the seam a dataset other than xBD plugs into, same swap pattern as `DamageModel`. |
| `xbd.py` | `XbdDataset`, the only implementation: parses xBD's on-disk layout and label JSON, and normalizes xBD's raw damage `subtype` strings into `DamageClass`. |
| `validation.py` | `DatasetValidationError` and its subclasses (`MissingImageError`, `MissingAnnotationError`, `InvalidImageFileError`, `MalformedAnnotationError`) plus the file-existence/decodability checks that raise them. |
| `preprocessing.py` | Re-exports `ImagePreprocessor`/`PreprocessConfig` from `app.ml.preprocessing` for resize/normalize, plus `AugmentationHook` (interface only) and `NoOpAugmentation` (its only implementation today). |

### 1–2. What xBD is, and why it fits SentinelAI

[xBD](https://arxiv.org/abs/1911.09296) (the dataset behind the xView2
challenge) is a large public dataset of paired pre-disaster and
post-disaster satellite imagery, with every building polygon-annotated and
labeled with a damage severity. It spans many distinct disaster events
across hurricanes, wildfires, floods, earthquakes, volcanic eruptions, and
tsunamis. It fits SentinelAI directly: it's the closest public dataset to
this platform's actual task (building-level damage severity from aerial/
satellite disaster imagery), large and diverse enough to support transfer
learning, and its four-class damage scale
(`no-damage`/`minor-damage`/`major-damage`/`destroyed`) is exactly what
`app.ml.schemas.DamageClass` already models.

### 3. What the model will eventually predict

Per building, per image: a `DamageClass` (`no_damage`/`minor`/`major`/
`destroyed`) and a confidence — exactly the `BuildingDamage` shape defined
in `app/ml/schemas.py`. Nothing about that contract changes for this
milestone; the dataset pipeline exists to eventually produce training
examples in that same shape (see `DatasetSample`/`BuildingAnnotation`
above), not to redefine it.

### 4. Why pre/post-disaster imagery matters

A single post-disaster image alone often can't distinguish "this building
was always like this" from "this building was damaged by the disaster" —
damage is fundamentally a *change*, and the reliable way to detect a
change is to compare before and after. This is why `ImageSample` carries
`pre_image_path` and `post_image_path` separately rather than only a
single `image_path`, and why `DamageModel.predict()`'s eventual extension
to pre/post pairs (see above) matters for real accuracy, not just as a
nice-to-have.

### 5–6. Data leakage and why disaster-level splitting matters

**How leakage happens here:** images from the *same disaster event* are
geographically clustered and visually correlated — overlapping terrain,
the same lighting/weather/imaging pass, the same building styles and
damage patterns. If two tiles from the same event end up on opposite sides
of a train/validation split, the model can partly "recognize the event"
rather than generalize the damage signal — validation accuracy looks
better than the model actually is at assessing damage in a disaster it's
never seen. Splitting at the *image* level (or randomly) makes this easy
to do by accident.

**The fix — disaster-level separation:** `XbdDatasetConfig.split_assignment`
maps *disaster id* → split (not sample id → split, and not a percentage the
code computes itself). `XbdDataset.list_samples()` filters purely by each
sample's disaster id, so every sample from one disaster — including its
pre/post pair, which always travel together as one `ImageSample` — lands
in exactly one split. A disaster discovered on disk with no entry in
`split_assignment` raises `DatasetValidationError` rather than silently
defaulting anywhere; there is no path for a disaster to end up unassigned
or split across partitions. Deciding *which* disasters go in which split
is left to the caller (a research decision, not one this module should
make silently); a future script to propose a balanced assignment is a
natural next step, not implemented here.

### 7. Where to place the dataset locally

Download xBD yourself (registration is required directly from the dataset
maintainers) and place it anywhere on disk — `XbdDatasetConfig.root` points
at it explicitly, so there's no fixed required location. A layout under
`datasets/` (see [`datasets/README.md`](../../datasets/README.md), which
already documents that raw datasets are never committed) such as
`datasets/xbd/` works well, matching the expected `images/`/`labels/`
subdirectory layout described in `app/ml/datasets/xbd.py`. **Nothing in
this codebase downloads xBD automatically or commits any dataset file** —
`*.tif`/`*.tiff`/`*.geotiff` are already gitignored repo-wide, and
`datasets/*` is gitignored except its own `README.md`/`samples/`.

### A note on verification

`xbd.py`'s parsing targets xBD's publicly documented release format, from
the published dataset description — it has **not** been validated against
a real, downloaded copy of xBD in this environment (this sandbox has no
internet access). The module docstring in `xbd.py` flags this explicitly.
Before relying on this for real training data, validate the filename and
label-JSON parsing against actual sample files and adjust if they differ —
this is exactly why `list_samples`/`load_image_sample`/`load_annotations`
fail loudly on anything unexpected rather than silently skipping it.

## Disaster Intelligence Core (Milestone F2)

The first version of the domain model and deterministic decision layer
for the future response-orchestration pipeline (`app/intelligence/`,
`app/services/intelligence_repository.py`,
`app/services/intelligence_service.py`,
`app/api/v1/endpoints/intelligence.py`). See
[`docs/architecture/intelligence.md`](../../docs/architecture/intelligence.md)
for the full architecture, pipeline diagram, and per-stage rationale —
this section is a summary.

### Domain model (`app/intelligence/schemas.py`)

Thirteen typed concepts: `Disaster`, `Observation`, `AffectedArea`,
`SearchZone`, `Hazard`, `Resource`, `RescueTeam`, `Infrastructure`,
`Route`, `HazardPrediction`, `Recommendation`, `Evidence`, `Uncertainty`
— plus one computed, non-primary type, `CapabilityMatchResult`. Every
concept reuses existing types rather than duplicating them
(`Geometry`/`CoordinateReferenceSystem` from `app.ml.geospatial`,
`DamageClass` from `app.ml.schemas`, `AccessibilityStatus` from
`app.roads.schemas`, `RouteResult` from `app.routing.schemas`), and
every geometry-carrying field is paired with an explicit
`*_crs: CoordinateReferenceSystem` (defaulting to `IMAGE`, the
non-geographic default) — the same "never treat image-space coordinates
as geographic" discipline `BuildingDamage` already established, applied
one layer further out. Every entity carries `is_simulated: bool`.

### Search-priority scoring (`app/intelligence/search_priority.py`)

A deterministic **baseline heuristic** — not a validated
search-and-rescue triage model, the same honesty as the road-risk
formula (Milestone 6B):

```
priority_score = sum(value_i * weight_i for available factors)
                  / sum(weight_i for available factors)
```

Four factors (damage severity, accessibility, population exposure,
evidence strength), every weight sourced from `SearchPriorityConfig`
(`app/intelligence/config.py`, itself from `Settings.SEARCH_PRIORITY_*`
— see `app/core/config.py`). A factor with no underlying data (e.g. no
`affected_population` on file) is **omitted and the remaining weights
renormalized** — never treated as `0` (would silently penalize) or
guessed. Every omission is recorded in `SearchZone.missing_factors` and
escalates `SearchZone.uncertainty` one level. A `SearchZone` is never a
claim a person is located there.

### Capability matching (`app/intelligence/capability_matching.py`)

Given a target and a list of `Resource`s, answers four questions
**separately**, never collapsed into one opaque score: can this
resource perform the task (exact capability-set match), is it currently
available, can it reach the target (great-circle distance, only when
both locations are explicitly tagged `WGS84` — otherwise `UNKNOWN`,
never guessed), and is the route operational (a documented
simplification: checked via the resource's own blocking operational
constraints, not a full per-candidate route computation — see the
module docstring for why). A capability mismatch or unavailability
always outranks proximity — the nearest resource is not automatically
the best one.

### Recommendation engine (`app/intelligence/recommendation.py`)

Three rule-based, deterministic rules — **no LLM, no ML model**:
a high-priority search zone with incomplete evidence recommends
reconnaissance; one with sufficient evidence and an eligible resource
recommends deployment; one with no eligible resource recommends
escalation. A non-operational bridge/road/tunnel recommends inspection
before dispatch. A high/critical hazard recommends avoiding the route.
Every `Recommendation` carries a non-empty `rationale`, `supporting_evidence`,
and `uncertainty`. If nothing meets the action threshold, the engine
returns one explicit `hold_pending_more_information` recommendation
rather than a bare empty list.

### Hazard prediction — deliberately unimplemented

`app/intelligence/hazard_prediction.py::unavailable_prediction()` is the
**only** way this codebase constructs a `HazardPrediction` — always
`status="unavailable"`, `probability=None`. No predictive hazard model
exists in this milestone; the schema exists so a real model can be
plugged in later without an API-contract change.

### Demo scenario (`app/intelligence/demo_scenario.py`)

One deterministic, fully `is_simulated=true` scenario, seeded into the
in-memory repository once at process start (`app/api/deps.py`) — there
is no ingestion endpoint yet, so without this seed the four
`/api/v1/intelligence/*` endpoints would be permanently unreachable.
Every id is generated via `uuid5(NAMESPACE_URL, ...)` from a fixed name
string (not `uuid4()`), so the scenario — and every id in it — is
byte-for-byte identical on every run, forever. Coordinates are centered
on `(1.5, 1.5)`, the same deliberately fictional open-ocean point the
frontend's own demo fixtures use. Built to demonstrate that **having
equipment is not enough**: it includes a capable-but-`unavailable`
resource (a real drone/excavator/team exists but can't deploy), a
resource that's available and reachable but lacks the required
capability, and exactly one resource that passes all four capability-
matching gates.

### Repository (`app/services/intelligence_repository.py`)

`InMemoryIntelligenceRepository` — same in-memory-placeholder tradeoff
and PostGIS-migration story as `InMemorySpatialRepository`/
`InMemoryRoadNetworkRepository`. `SearchZone`s and `Recommendation`s are
**not** stored: both are pure functions of the repository's raw inputs
plus config, recomputed fresh on every request (cheap — no ML
inference, no network I/O) rather than cached and risking staleness.

### Do not implement (this milestone)

- No ML-based hazard/search prediction model — `HazardPrediction` is
  interface-only (see above).
- No LLM-based recommendation generation — the engine is entirely
  rule-based.
- No real-disaster ingestion endpoint — only the deterministic demo
  scenario is servable.
- No per-candidate route computation in capability matching — route
  operability is inferred from known operational constraints, not a
  full routing-engine query per resource-target pair.
- No persistence — the repository is in-memory, like every other
  repository in this codebase today.

## Analysis-Aware Intelligence (Milestone F3)

Connects the Disaster Intelligence Core (above) to the *real* analysis
pipeline's outputs — `app/intelligence/analysis_adapter.py`,
`app/services/analysis_intelligence_service.py`,
`app/api/v1/endpoints/analysis.py`'s three `.../intelligence[...]`
routes. See
[`docs/architecture/intelligence.md`](../../docs/architecture/intelligence.md),
"Milestone F3," for the full design; this section is a summary.

```
User Upload -> Analysis -> Damage/Risk/Infrastructure Observations
            -> Intelligence Context -> Search Priority
            -> Resource Capability Matching -> Route Feasibility
            -> Response Recommendation -> Command Center UI
```

**Not a second intelligence system** — F3 adds exactly one adapter
(`build_context_from_analysis`) that turns an already-completed
analysis's real `DamageAnalysis`/`list[BuildingDamage]`/`RoadRiskResponse`
into an F2 `DisasterScenario`, then reuses F2's search-priority/
capability-matching/recommendation engines completely unmodified.

### `analysis_id` vs `disaster_id`

Kept as genuinely separate concepts, not renamed or merged:
`app.intelligence.analysis_adapter.derive_disaster_id(analysis_id) ->
UUID` is a pure, deterministic `uuid5(...)` derivation — never stored,
never cached, recomputed fresh on every request. See the architecture
doc for the alternatives considered and why this is the smallest clean
solution.

### Missing-data behavior

`build_context_from_analysis` returns an explicit unavailable reason —
never a fabricated or silently-empty scenario — for: the analysis not
being `COMPLETED` yet, a `MODEL_UNAVAILABLE`/`INFERENCE_FAILURE`
analysis failure (the same `AnalysisErrorCode` values reused verbatim),
zero buildings (`INSUFFICIENT_EVIDENCE`), or zero *georeferenced*
buildings (`NO_GEOREFERENCE`). Only `BuildingDamage` records that are
both `georeferenced=True` **and** explicitly tagged
`CoordinateReferenceSystem.WGS84` become `AffectedArea`s — the same
defense-in-depth CRS check `RoadRiskService._is_usable()` already
applies, re-verified here rather than trusted from a single flag.

### Route feasibility

For the single top-ranked, otherwise-eligible resource candidate against
the single top-priority search zone, `analysis_intelligence_service.py`
calls the real `RoutingService.route()` — the same engine
`POST /api/v1/routing` uses, never a second pathfinder or invented
geometry. Reported as one of `"computed"` (a real, possibly
`found=false`, `RouteResult`), `"route_unavailable"` (no road network
loaded, or a location isn't tagged `EPSG:4326`), or `"not_applicable"`
(an earlier gate failed, or this candidate wasn't the top-ranked one —
route feasibility is deliberately bounded to one candidate per request).

### DEMO vs ANALYSIS

No real resource-ingestion system exists, so the resource pool for any
analysis-derived scenario reuses `build_demo_scenario().resources`
verbatim — `resources_are_demo: true` unconditionally in every F3
response, independent of whether the surrounding analysis (and its
search zones/recommendations, `is_simulated: false`) is real. The
frontend's Demo mode is a wholly separate, hand-authored fixture path
(`apps/web/src/lib/demo/demo-data.ts`) that never calls these endpoints
at all — see `docs/architecture/frontend.md`.

### Do not implement (this milestone)

- No change to F2's scoring/matching/recommendation math — F3 is
  purely an adapter plus a route-feasibility enrichment step.
- No real resource-ingestion system — the demo resource pool is reused,
  always explicitly flagged `resources_are_demo: true`.
- No per-candidate routing beyond the single top-ranked candidate.
- No change to any existing analysis (`/api/v1/analysis/{id}[...]`) or
  F2 disaster-scoped (`/api/v1/intelligence/{disaster_id}[...]`)
  endpoint — both are unchanged and fully backward compatible.

## Production infrastructure (Milestone F5)

Real PostgreSQL persistence, a Redis-backed background job queue, and a
separate worker process that owns the real CLIP model — see
[`docs/architecture/production.md`](../../docs/architecture/production.md)
for the full architecture; this section is a summary.

```
POST /api/v1/analysis
  -> persist (PostgreSQL) -> store image (object storage)
  -> enqueue (Redis/RQ) -> 201, immediately
       |
       v
   worker process (python -m app.worker.main)
  -> AnalysisProcessingService.process() [unchanged from Milestone 4]
  -> persisted result
```

**The API process never imports `torch`/`open_clip` and never loads the
model** — fixing F4's own documented 40-150s in-request cold start.
Only `app/worker/main.py` (a separate process/entrypoint) does, once, at
its own startup, publishing readiness to Redis
(`GET /api/v1/model/status` reads it back — the API never constructs a
`DamageModel` merely to answer that endpoint).

**Persistence**: two tables (`analyses`, `building_damages` —
`app/db/models.py`), not a one-to-one mirror of every schema. Search
zones/recommendations/routes are deliberately **not** persisted — F2/F3's
own "recompute fresh, never cache" design principle already applies;
see `docs/architecture/production.md`, "Persistence," for the full
reasoning. `PostgresAnalysisRepository`/`PostgresSpatialRepository`
implement the exact same Protocols the pre-existing in-memory
repositories do — production DI swaps to them; the in-memory
implementations are unchanged and still back every test.

**Migrations**: Alembic (`apps/api/alembic/`) —
`alembic upgrade head`. Reads `Settings.DATABASE_URL`, never a second
hardcoded connection string.

**Queue**: RQ (Redis Queue), not Celery — "do not add Celery solely
because it is popular" when RQ's `enqueue`/`Worker` over a plain Redis
list already solves this system's actual problem. `RedisJobQueue`
(production) / `InMemoryJobQueue` (test-only, synchronous).

**Idempotency was already structurally guaranteed before F5** —
`AnalysisProcessingService.process()`'s existing terminal-state guard
plus every repository's replace- (not append-) semantics. F5's job was
to verify this and add bounded retries (`JOB_MAX_RETRIES`, RQ's
`Retry`) for the one class of failure that genuinely needs it —
infrastructure exceptions that already propagate un-guarded out of
`process()`'s own existing structure.

**Health/readiness**: `GET /health` (liveness only) is unchanged;
`GET /ready` (new) gates on real PostgreSQL + Redis connectivity, with
model status reported but never gating — a request can be accepted
while the model is still loading.

**Docker**: `docker compose up --build` — see
[`docker/README.md`](../../docker/README.md). One image
(`docker/api.Dockerfile`), two roles (`api`: `uvicorn`; `worker`:
`python -m app.worker.main`), plus `postgres`/`redis`/a one-shot
`migrate` service.

### Do not implement (this milestone)

- No authentication/authorization.
- No cloud deployment, autoscaling, or high availability — Docker
  Compose is a local production-*style* stack, not a deployment target.
- No object storage backend beyond local disk (`LocalObjectStorage`) —
  the interface is designed for S3/R2/GCS later, not built here.
- No multi-worker horizontal scaling tested (RQ supports it natively;
  `docker-compose.yml` runs one `worker` service).
- No dead-letter/poison-queue inspection tooling.

## Project layout

```
app/
├── main.py                    # Application factory (create_app())
├── core/
│   ├── config.py                # Settings (pydantic-settings) — no FastAPI imports
│   ├── logging.py                # logging.dictConfig-based setup
│   └── constants.py               # API_V1_PREFIX, allowed image types, and other app-wide constants
├── api/
│   ├── router.py                 # Top-level router: aggregates root, health, and v1
│   ├── deps.py                     # Shared dependency providers
│   ├── exception_handlers.py        # Maps service-layer errors to HTTP responses
│   ├── root.py                       # Unversioned GET /
│   ├── health.py                      # Unversioned GET /health, GET /ready (Milestone F5)
│   └── v1/                             # Versioned routers, mounted under /api/v1
│       ├── router.py
│       └── endpoints/ {status.py, system.py, analysis.py, roads.py, routing.py, intelligence.py}
├── services/
│   ├── system_service.py             # Backing service/DI scaffold (Milestone 1)
│   ├── analysis_service.py            # Orchestrates upload validation, storage, metadata
│   ├── image_validation.py             # Pillow-based content validation
│   ├── file_storage.py                  # FileStorage protocol + LocalFileStorage
│   ├── analysis_repository.py            # In-memory analysis metadata store
│   ├── analysis_processing_service.py     # Milestone 4: lifecycle orchestration (enqueue/process/get_analysis)
│   ├── spatial_repository.py               # Milestone 5: SpatialRepository protocol + InMemorySpatialRepository
│   ├── damage_map_service.py                # Milestone 5: assembles the damage-map response
│   ├── road_network_repository.py            # Milestone 6A: RoadNetworkRepository + InMemory impl
│   ├── road_network_ingestion_service.py      # Milestone 6A: OSM acquisition -> construction -> repository
│   ├── road_network_status_service.py          # Milestone 6A: assembles the roads/status response
│   ├── road_risk_service.py                     # Milestone 6B: assembles the road-risk response
│   ├── routing_service.py                        # Milestone 6C: assembles routing/comparison results
│   ├── incident_intelligence_service.py           # Milestone 7: assembles the incident briefing
│   ├── intelligence_repository.py                  # Milestone F2: DisasterScenario storage (in-memory)
│   ├── intelligence_service.py                      # Milestone F2: orchestrates the F2 pipeline
│   ├── analysis_intelligence_service.py               # Milestone F3: analysis -> intelligence -> route feasibility
│   ├── postgres_analysis_repository.py                  # Milestone F5: PostgreSQL-backed AnalysisRepository
│   ├── postgres_spatial_repository.py                    # Milestone F5: PostgreSQL-backed SpatialRepository (same table)
│   ├── job_queue.py                                       # Milestone F5: JobQueue protocol, RedisJobQueue, InMemoryJobQueue
│   ├── worker_status.py                                    # Milestone F5: Redis-backed model-lifecycle publish/read channel
│   ├── model_status_service.py                              # Milestone F4; F5: reads worker_status, never loads the model
│   ├── readiness_service.py                                  # Milestone F5: GET /ready — real DB/Redis checks
│   └── exceptions.py                              # Domain errors (no FastAPI dependency)
├── db/                          # Milestone F5 — see docs/architecture/production.md
│   ├── models.py                  # AnalysisORM, BuildingDamageORM (SQLAlchemy declarative)
│   └── session.py                   # Engine/session-factory cache, keyed by DATABASE_URL
├── worker/                      # Milestone F5 — the background worker process
│   ├── main.py                    # Entrypoint (`python -m app.worker.main`): eager model load + RQ Worker loop
│   └── tasks.py                     # process_analysis_job() — the actual per-job function RQ invokes
├── ml/                          # Damage-intelligence architecture (Milestones 3A + 3C) — see above
│   ├── schemas.py
│   ├── spatial.py                 # BoundingBox
│   ├── model.py                    # DamageModel protocol, RawDetection, UnavailableDamageModel
│   ├── localizer.py                 # Stage 1: BuildingLocalizer protocol, UnavailableBuildingLocalizer
│   ├── classifier.py                 # Stage 2: TorchDamageClassifier (ResNet18 baseline)
│   ├── pipeline.py                    # TwoStageDamageModel — composes Stage 1 + Stage 2
│   ├── preprocessing.py
│   ├── postprocessing.py
│   ├── inference.py
│   ├── evaluation.py                   # precision/recall/F1/confusion matrix
│   ├── datasets/                        # Dataset pipeline (Milestone 3B) — see above
│   │   ├── schemas.py
│   │   ├── base.py
│   │   ├── xbd.py
│   │   ├── validation.py
│   │   └── preprocessing.py
│   └── geospatial/                      # Milestone 5 — see above and app/ml/geospatial/__init__.py
│       ├── geometry.py                    # Point/Polygon/BoundingBox geometry, validated
│       ├── crs.py                          # CoordinateReferenceSystem
│       ├── georeferencing.py                # GeoreferencingTransform, AffineGeoTransform
│       ├── spatial_builder.py                # BoundingBox -> (Geometry, CRS, georeferenced)
│       ├── priority.py                        # DamagePriority (damage-based only)
│       └── geojson.py                          # Feature/FeatureCollection (RFC 7946)
├── roads/                       # Milestone 6A — see above and app/roads/__init__.py
│   ├── schemas.py                 # AccessibilityStatus, RoadNode, RoadEdge, RoadGraph
│   ├── errors.py                   # InvalidRoadGraphError, UnknownRoadNodeError, RoadNetworkSourceError
│   ├── weighting.py                  # compute_base_cost() — the future risk-weighting seam
│   ├── geo_utils.py                   # haversine_distance_meters()
│   ├── osm_source.py                   # OSM acquisition: RoadNetworkSource, OverpassRoadNetworkSource
│   └── builder.py                       # Graph construction: build_road_network()
├── risk/                        # Milestone 6B — see above and app/risk/__init__.py
│   ├── config.py                  # RoadRiskConfig, sourced from Settings' ROAD_RISK_* fields
│   ├── formula.py                   # The baseline heuristic math (severity/decay/aggregation/levels)
│   ├── spatial.py                     # point_to_segment_distance_meters(), bbox pre-filter
│   └── analyzer.py                      # compute_road_risk() — the Spatial Relationship pipeline
├── routing/                     # Milestone 6C — see above and app/routing/__init__.py
│   ├── config.py                  # RoutingConfig, sourced from Settings' ROUTING_* fields
│   ├── accessibility.py             # Traversability, resolve_accessibility()
│   ├── cost.py                        # build_edge_cost_fn() — reuses app.risk.formula unmodified
│   ├── algorithm.py                     # shortest_path() — Dijkstra, optionally A*; GraphView
│   ├── nearest_node.py                    # InMemoryNearestNodeLocator
│   ├── result_builder.py                    # PathResult -> RouteResult
│   ├── metrics.py                             # detour_ratio(), risky/blocked-segment counts
│   └── geojson.py                               # route_to_feature() (RFC 7946 LineString)
├── incident/                    # Milestone 7 — see above and app/incident/__init__.py
│   ├── schemas.py                 # IncidentContext, LLMNarrativeOutput, IncidentBriefing
│   ├── config.py                    # IncidentConfig, sourced from Settings' INCIDENT_* fields
│   ├── context_builder.py             # build_incident_context() — damage/road-risk/route -> IncidentContext
│   ├── severity.py                      # classify_incident_severity(), classify_confidence()
│   ├── prompt.py                          # PROMPT_VERSION, SYSTEM_PROMPT, build_user_message()
│   ├── provider.py                          # LLMProvider protocol, LLMProviderError/LLMTimeoutError
│   ├── fallback.py                            # build_fallback_narrative(), DeterministicSummaryProvider
│   ├── mock_provider.py                         # MockLLMProvider (test-only)
│   ├── anthropic_provider.py                      # AnthropicLLMProvider (the one real provider)
│   ├── validator.py                                 # parse_llm_output() — Pydantic-validated JSON parsing
│   ├── grounding.py                                   # filter_unsupported_claims()
│   └── briefing_builder.py                              # assemble_briefing()
├── intelligence/                # Milestone F2 — see above and app/intelligence/__init__.py
│   ├── schemas.py                 # The 13 domain concepts + CapabilityMatchResult
│   ├── config.py                    # SearchPriorityConfig, CapabilityMatchingConfig
│   ├── search_priority.py             # Deterministic baseline search-priority scorer
│   ├── capability_matching.py           # Deterministic capability matcher
│   ├── recommendation.py                  # Rule-based recommendation engine
│   ├── hazard_prediction.py                 # unavailable_prediction() — no ML model exists yet
│   ├── demo_scenario.py                       # build_demo_scenario() — deterministic, is_simulated=true
│   └── analysis_adapter.py                      # Milestone F3: DamageAnalysis+BuildingDamage+RoadRiskResponse -> DisasterScenario
├── schemas/                    # Pydantic request/response models
├── utils/                      # Generic helpers with no business meaning (datetime, sanitize)
└── middleware/                  # CORS policy, request logging
alembic/                        # Milestone F5 — migrations (alembic upgrade head)
├── env.py                        # Reads Settings.DATABASE_URL, never a hardcoded URL
└── versions/0001_initial.py        # analyses, building_damages
tests/                          # pytest suite
```

**Layering rule:** routes in `app/api` only translate HTTP ↔ Pydantic
models and call a service; anything resembling a decision, validation, or
I/O belongs in `app/services`, where it's testable without the HTTP layer.
`POST /api/v1/analysis` follows: route → `AnalysisService` → `FileStorage` /
`image_validation`. `app/ml/` follows the same rule one level further
removed — it has no FastAPI or `app/api` import at all.

## Commands

```bash
pytest              # run tests
ruff check .        # lint
ruff format .       # format
mypy .              # type-check
```

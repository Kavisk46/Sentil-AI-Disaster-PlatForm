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
lifecycle," below. Still no database or authentication.

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
respond to) and never invents a prediction to paper over a missing model:

- `ModelNotAvailableError` (raised by `TwoStageDamageModel` — currently
  always, since Stage 1 has no real localizer; see "Why Stage 1 has no
  real implementation yet," below) is caught and saved as `failed` with
  `AnalysisErrorCode.MODEL_UNAVAILABLE` and a message describing which
  stage was unavailable.
- Any other exception during inference is caught, logged with a full
  traceback server-side (`logger.exception`), and saved as `failed` with
  `AnalysisErrorCode.INFERENCE_FAILURE` and a generic, safe message. **The
  raw exception text/stack trace is never included in the API response.**

Either way, the API stays stable: `GET /api/v1/analysis/{id}` still
returns `200` with a well-formed `DamageAnalysis` body — a structured
failure, not a `500` or a hang. Because no building-localization model
exists yet (see "Why Stage 1 has no real implementation yet," below),
**every analysis through the real, unmodified production wiring today
ends up `failed` with `MODEL_UNAVAILABLE`** — this is the honest,
expected behavior of a system with no trained model, not a bug.

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
type regardless of which stage is missing.

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

- **No trained model exists.** Every component in this section is real,
  tested infrastructure — none of it currently produces a genuine damage
  prediction end-to-end, because Stage 1 is always unavailable and Stage 2
  has no checkpoint.
- **Stage 1 (building localization) has no implementation plan committed
  yet beyond the interface** — see "Why Stage 1 has no real implementation
  yet," above.
- **No pre/post-disaster comparison** — post-disaster image only (a
  documented Milestone 3A/3B decision, unchanged).
- **No calibrated confidence** — see "Confidence interpretation," above.
- **No geospatial (latitude/longitude) output** — `BoundingBox` is pixel-space
  only; see "Geospatial future support," below.
- **This system does not predict, and cannot currently be used to predict,
  tsunamis, earthquakes, floods, or any other hazard** — its only intended
  eventual capability is post-hoc building damage severity from imagery of
  a disaster that has already occurred.
- When a real model eventually exists, expect accuracy well below
  published xView2 leaderboard numbers (which use full data, heavy
  augmentation, and often GPU-scale ensembles) — this baseline
  deliberately trades peak accuracy for a fast, honest, working pipeline.

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
model available" — it risks misdirecting rescue resources. Every stage in
this pipeline (`UnavailableBuildingLocalizer`, `TorchDamageClassifier`
with no checkpoint, `UnavailableDamageModel`) fails loudly rather than
returning a placeholder result, and every `ModelStatus.model_loaded` is
computed from real state, never hardcoded `True`.

### Research integrity: four distinct things, not one

This codebase distinguishes, and this document uses the terms
deliberately:

1. **Model infrastructure** — the `DamageModel`/`BuildingLocalizer`
   Protocols, `TwoStageDamageModel`, preprocessing/postprocessing. Exists
   today, fully tested, produces no predictions on its own.
2. **A pretrained model** — e.g. ImageNet weights for the ResNet18
   backbone. Not currently loaded by any shipped code path (see "Training
   vs. inference"); used only as an external training starting point.
3. **A fine-tuned model** — a checkpoint actually trained on xBD. **Does
   not exist.** `Settings.MODEL_PATH` is unset by default and nothing in
   this repository provides a checkpoint.
4. **An evaluated model** — a fine-tuned model with measured metrics via
   `evaluate_classification()`. **Does not exist**, since step 3 doesn't.

Nothing in this codebase represents an untrained or unavailable model as
an operational damage predictor.

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
│   ├── health.py                      # Unversioned GET /health
│   └── v1/                             # Versioned routers, mounted under /api/v1
│       ├── router.py
│       └── endpoints/ {status.py, system.py, analysis.py, roads.py, routing.py}
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
│   └── exceptions.py                              # Domain errors (no FastAPI dependency)
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
├── schemas/                    # Pydantic request/response models
├── utils/                      # Generic helpers with no business meaning (datetime, sanitize)
└── middleware/                  # CORS policy, request logging
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

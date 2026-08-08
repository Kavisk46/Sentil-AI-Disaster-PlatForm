# Backend Architecture

The backend is the system of record for SentinelAI: it ingests imagery and
field data, persists geospatial records, exposes the API the frontend and
external integrations consume, and coordinates work handed off to the AI
engine and routing subsystem.

## Responsibilities

- Accept and validate incoming imagery metadata and field reports.
- Persist incidents, imagery, detections, routes, and briefings as geospatial
  records.
- Expose a versioned REST API for all read and write operations used by the
  frontend.
- Coordinate asynchronous processing jobs handed off to the AI engine
  (detection, briefing generation) and the routing subsystem.

## Structure

The backend (`apps/api`) is a Python 3.12 service built on FastAPI, using
Pydantic v2 for request/response validation. It follows a Clean
Architecture layering so framework, configuration, and API concerns stay
separated from the domain and persistence logic added from Phase 2 onward:

- **`app/core`** — settings (`pydantic-settings`), logging configuration, and constants. No FastAPI imports here.
- **`app/api`** — versioned routers (`app/api/v1`) and their endpoint modules; `/health` is deliberately kept unversioned.
- **`app/middleware`** — CORS policy and request-logging middleware.
- **`app/schemas`** — Pydantic response models. Currently infrastructure-only (`HealthResponse`, `ServiceInfoResponse`); domain schemas (incident, imagery, detection, route, briefing) are added once persistence work begins.
- **`app/main.py`** — the application factory (`create_app()`) that wires settings, logging, middleware, and routers together in one place.

Persistence (PostgreSQL/PostGIS via async SQLAlchemy) and the job
coordination layer for dispatching work to the AI engine and routing
subsystem are added starting in Phase 2 — no database is present yet.

## Key Interactions with Other Subsystems

- Is the sole interface the [frontend](frontend.md) uses to read and write
  data — the frontend never accesses the database or AI engine directly.
- Dispatches imagery for processing to the [AI engine](ai-engine.md) and
  persists the resulting detections.
- Supplies the current road network and detected hazards to the
  [routing subsystem](routing.md) and persists computed routes.

## API Contract

The concrete API surface is documented in [`docs/api/endpoints.md`](../api/endpoints.md) as it is implemented.

## Status

The engineering foundation — app factory, settings, logging, CORS,
request-logging middleware, API versioning, and `/health` — was delivered
in Sprint 1. Domain models, persistence, and business endpoints are added
starting in **Phase 2** of [`PROJECT_ROADMAP.md`](../../PROJECT_ROADMAP.md).

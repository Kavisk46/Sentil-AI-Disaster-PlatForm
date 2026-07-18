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

## Intended Structure

The backend is a Python service built on FastAPI, using Pydantic for request
and response validation and async SQLAlchemy for data access against a
PostgreSQL/PostGIS database.

Planned top-level organization within `backend/`:

- **API layer** — versioned route definitions and request/response schemas.
- **Domain models** — incident, imagery, detection, route, and briefing
  entities, including their geospatial representations.
- **Persistence layer** — database access and migrations.
- **Job coordination** — interfaces for dispatching work to the AI engine and
  routing subsystem and receiving results.
- **Configuration & observability** — structured logging, health checks, and
  environment-based configuration.

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

Backend implementation begins in **Phase 2** of [`PROJECT_ROADMAP.md`](../../PROJECT_ROADMAP.md). This document will be expanded with concrete schema and endpoint detail as that phase begins.

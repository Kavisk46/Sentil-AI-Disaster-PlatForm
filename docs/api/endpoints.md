# API Reference

This document describes SentinelAI's versioned REST API surface: the
endpoints the frontend and external integrations use to read and write
incidents, imagery, detections, routes, and briefings.

## Currently Implemented

The backend foundation milestone delivers infrastructure-level endpoints
only — no domain data yet.

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

Interactive OpenAPI docs are available at `/docs` (Swagger UI) and `/redoc`
whenever the API is running.

## Planned Structure

Domain endpoints are added starting in **Phase 2 — Backend** of
[`PROJECT_ROADMAP.md`](../../PROJECT_ROADMAP.md), grouped by resource
following the domain model described in
[`docs/architecture/backend.md`](../architecture/backend.md):

- **Incidents** — creating and querying disaster incidents.
- **Imagery** — uploading and retrieving aerial/satellite imagery and its metadata.
- **Detections** — querying AI-detected damage and infrastructure impact records.
- **Routes** — requesting and retrieving computed rescue/access routes.
- **Briefings** — retrieving generated operational briefings for an incident.

For each, this document will describe the HTTP method and path, request/response
schemas, authentication requirements, and example requests.

## Versioning

The API is versioned via a URL path prefix (`/api/v1/...`, see
`app/core/constants.py`) so breaking changes can be introduced in a new
version without disrupting existing integrations.

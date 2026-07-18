# API Reference

This document will describe SentinelAI's versioned REST API surface: the
endpoints the frontend and external integrations use to read and write
incidents, imagery, detections, routes, and briefings.

## Status

The API is designed and implemented as part of **Phase 2 — Backend** in
[`PROJECT_ROADMAP.md`](../../PROJECT_ROADMAP.md). No endpoints exist yet; this
document is the intended home for that reference once the backend service is
implemented.

## Planned Structure

Once implemented, this document will describe, for each endpoint:

- HTTP method and path
- Request parameters and body schema
- Response schema
- Authentication and authorization requirements
- Example requests and responses

Endpoints will be grouped by resource, following the domain model described
in [`docs/architecture/backend.md`](../architecture/backend.md):

- **Incidents** — creating and querying disaster incidents.
- **Imagery** — uploading and retrieving aerial/satellite imagery and its metadata.
- **Detections** — querying AI-detected damage and infrastructure impact records.
- **Routes** — requesting and retrieving computed rescue/access routes.
- **Briefings** — retrieving generated operational briefings for an incident.

## Versioning

The API will be versioned via a URL path prefix (e.g., `/api/v1/...`) so that
breaking changes can be introduced in a new version without disrupting
existing integrations.

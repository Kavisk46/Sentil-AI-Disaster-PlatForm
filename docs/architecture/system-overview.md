# System Overview

This document describes SentinelAI's high-level architecture: the major
subsystems, how data flows between them, and the design principles that
guide how they are decomposed. Component-level detail for each subsystem
lives in its own document in this directory.

## Subsystems

SentinelAI is composed of four major subsystems:

| Subsystem | Responsibility | Detail |
|---|---|---|
| **Frontend** | Responder-facing web application for visualization and decision support | [`frontend.md`](frontend.md) |
| **Backend** | API, persistence, and geospatial data services | [`backend.md`](backend.md) |
| **AI Engine** | Damage detection, infrastructure classification, and briefing generation | [`ai-engine.md`](ai-engine.md) |
| **Routing** | Hazard-aware rescue and access route computation | [`routing.md`](routing.md) |

## End-to-End Data Flow

1. **Ingestion** — Aerial or satellite imagery, along with any available field
   reports, enters the platform through the backend's ingestion API.
2. **Detection** — The AI engine processes ingested imagery to detect damage
   and classify affected infrastructure.
3. **Geospatial persistence** — Detected findings are stored as geospatial
   records (PostGIS) alongside the source imagery metadata.
4. **Routing** — The routing engine consumes the current road network together
   with detected hazards to compute viable access and rescue routes.
5. **Briefing generation** — The AI engine synthesizes an operational briefing
   from the structured detections and routing output.
6. **Presentation** — The frontend queries the backend API to render the map,
   detections, routes, and briefings for responders.

## Cross-Cutting Design Principles

- **API-first boundaries.** Every subsystem communicates through the backend's
  versioned API rather than shared databases or direct calls, so subsystems
  can evolve and scale independently.
- **Statelessness where possible.** Application services avoid holding
  session or processing state in memory beyond a single request/job, so any
  instance can be scaled horizontally.
- **Explicit data contracts.** Geospatial and detection data structures are
  defined once (as shared schemas) and consumed consistently by the backend,
  AI engine, and frontend.
- **Observability by default.** Every service is expected to emit structured
  logs and health signals sufficient to diagnose failures in a live incident
  response scenario, where downtime has real-world consequences.

## Related Documents

- [`docs/api/endpoints.md`](../api/endpoints.md) — API surface consumed by the frontend and external integrations.
- [`docs/research/literature-review.md`](../research/literature-review.md) — Research basis for the AI engine's approach.
- [`PROJECT_ROADMAP.md`](../../PROJECT_ROADMAP.md) — Phased plan for implementing each subsystem.

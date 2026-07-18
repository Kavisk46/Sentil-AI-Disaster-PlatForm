# Docker

This directory holds the Dockerfile for each SentinelAI service, referenced
by the root [`docker-compose.yml`](../docker-compose.yml).

| Dockerfile | Service | Added in |
|---|---|---|
| `backend.Dockerfile` | Backend API service | Phase 2 — Backend |
| `frontend.Dockerfile` | Frontend web application | Phase 3 — Frontend |
| `ai.Dockerfile` | AI engine (detection & briefing generation) | Phase 4 — AI Integration |

No Dockerfiles exist yet. The root `docker-compose.yml` currently provisions
only the shared infrastructure (PostgreSQL/PostGIS and Redis) that these
services will depend on once implemented; the application service
definitions are present in that file as commented-out scaffolding, ready to
be enabled as each Dockerfile above is added.

See [`PROJECT_ROADMAP.md`](../PROJECT_ROADMAP.md) for the phase in which each
service — and its corresponding Dockerfile — is implemented.

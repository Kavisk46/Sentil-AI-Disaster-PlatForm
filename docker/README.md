# Docker

This directory holds the Dockerfile for each SentinelAI service, referenced
by the root [`docker-compose.yml`](../docker-compose.yml). Every Dockerfile
uses the repository root as its build context (not its own subdirectory),
since the frontend is part of an npm workspaces monorepo and needs access to
`packages/` at build time.

| Dockerfile | Service | Status |
|---|---|---|
| `api.Dockerfile` | Backend API (`apps/api`) | Implemented — Sprint 1 |
| `web.Dockerfile` | Frontend web application (`apps/web`) | Implemented — Sprint 1 |
| `ai.Dockerfile` | AI engine (detection & briefing generation) | Not yet implemented — Phase 4 |

Sprint 1 provisions the frontend and backend only; no database or cache is
part of the stack yet. PostgreSQL/PostGIS will be added here alongside the
domain models introduced in Phase 2 — see
[`PROJECT_ROADMAP.md`](../PROJECT_ROADMAP.md).

## Running locally

```bash
docker compose up --build
```

- API: http://localhost:8000 (docs at `/docs`)
- Web: http://localhost:3000

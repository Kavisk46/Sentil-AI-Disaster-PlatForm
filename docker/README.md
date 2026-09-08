# Docker

This directory holds the Dockerfile for each SentinelAI service, referenced
by the root [`docker-compose.yml`](../docker-compose.yml). Every Dockerfile
uses the repository root as its build context (not its own subdirectory),
since the frontend is part of an npm workspaces monorepo and needs access to
`packages/` at build time.

| Dockerfile | Service(s) | Status |
|---|---|---|
| `api.Dockerfile` | `api`, `worker`, `migrate` (`apps/api` — one image, different commands) | Implemented |
| `web.Dockerfile` | `web` (`apps/web`) | Implemented |

Milestone F5 ("Production Infrastructure") added real persistence
(PostgreSQL), a background job queue (Redis + RQ), and a separate worker
process that eagerly loads the real CLIP damage-classification model at
its own startup — the API process itself never does. See
[`docs/architecture/production.md`](../docs/architecture/production.md)
for the full architecture.

## Running locally

```bash
docker compose up --build
```

- API: http://localhost:8000 (docs at `/docs`)
- Web: http://localhost:3000
- Readiness: http://localhost:8000/ready
- Model status: http://localhost:8000/api/v1/model/status

`migrate` runs `alembic upgrade head` once and exits before `api`/`worker`
start — a fresh `docker compose up` always applies the current schema to
a fresh Postgres volume. The worker's first CLIP load (40-150s, see
`apps/api/README.md`, "Milestone F4") happens in the background; `api`
and `web` are usable immediately regardless — `GET /api/v1/model/status`
honestly reports `MODEL_LOADING` until it finishes.

To reset entirely (drop all data, re-download the model on next start):

```bash
docker compose down -v
```

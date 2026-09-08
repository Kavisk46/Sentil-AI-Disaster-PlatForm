# Production Infrastructure (Milestone F5)

F5 turns SentinelAI from a well-tested local application (F1-F4) into a
deployable, production-*style* platform: real PostgreSQL persistence, a
Redis-backed background job queue, a separate worker process that owns
the real CLIP model, health/readiness semantics, structured logging, and
Docker Compose. It does not add authentication, cloud deployment,
autoscaling, or high availability — see "Known limitations," below, and
`apps/api/README.md`'s own "Do not implement" list.

## Architecture

```
                    API (FastAPI)
                         |
                    PostgreSQL  <───────────────┐
                         |                      |
                    Redis (job queue +          |
                    published model status)     |
                         |                      |
                      Worker  ────────────────────┘
                         |
                Analysis Pipeline (unchanged: F4's
                TwoStageDamageModel + DamageInferenceEngine)
                         |
                BuildingDamage → PostgreSQL
                         |
                F3 Intelligence (unchanged)
                         |
                API reads the persisted result / recomputes
                intelligence fresh on every request
```

`POST /api/v1/analysis` → persist (PostgreSQL) → store the image (object
storage) → enqueue (Redis/RQ) → return `201` immediately. The worker
dequeues, runs the *exact same* `AnalysisProcessingService.process()`
F4 already established, and persists the result. **The API process
never imports `torch`/`open_clip` and never loads the model** — only the
worker does, once, at its own startup.

## Persistence

Two tables, not a one-to-one mirror of every Pydantic schema:

- **`analyses`** (`app/db/models.py::AnalysisORM`) — the analysis
  lifecycle record: status, upload metadata, timestamps, the completed
  result's `summary`/`model_metadata` (stored as JSON — small, nested,
  never queried by internal field), failure code/message, and
  `attempt_count` (new in F5 — see "Idempotency/retries").
- **`building_damages`** (`BuildingDamageORM`) — one row per detected
  building, foreign-keyed to `analyses`, matching exactly what
  `app.services.spatial_repository`'s own module docstring already
  anticipated ("a real `geometry`/`geography` column... `save_buildings`
  becomes an INSERT/UPSERT into that `buildings` table").

**Deliberately NOT persisted**: `SearchZone`, `Recommendation`, `Route`.
F2/F3's own established, tested design principle is that these are
*pure functions* of `AffectedArea`/`Resource`/config, recomputed fresh
on every request specifically so they never go stale relative to a
config change (`IntelligenceService`'s own docstring: "computed fresh on
every call, never cached"). Persisting them would either silently
reintroduce that staleness or add a table that's read exactly once,
right after being (re)computed anyway — no real benefit either way.

`PostgresAnalysisRepository`/`PostgresSpatialRepository`
(`app/services/postgres_*.py`) implement the *exact same*
`AnalysisRepository`/`SpatialRepository` Protocols
`InMemoryAnalysisRepository`/`InMemorySpatialRepository` already define
— production DI (`app/api/deps.py`) swaps to them; nothing in
`AnalysisService`/`AnalysisProcessingService`/`DamageMapService`/
`RoadRiskService`/F3's `analysis_adapter` changes. The in-memory
implementations are preserved unchanged, still the default for tests.

`PostgresSpatialRepository.save_buildings()` is a deliberate no-op: in
Postgres, `AnalysisRepository` and `SpatialRepository` are two *views*
over the same physical `building_damages` table (the analysis
repository writes it, in `save_result()`, which
`AnalysisProcessingService._save_result()` always calls first) — writing
the row a second time would either duplicate it or need an ordering
dependency between the two calls that doesn't otherwise exist.

## Migrations

Alembic, `apps/api/alembic/`. `env.py` reads `Settings.DATABASE_URL` —
one source of truth for both the running application and migrations,
never a second hardcoded connection string.

```bash
cd apps/api
alembic upgrade head        # apply every pending migration
alembic revision --autogenerate -m "description"   # generate a new one
alembic downgrade -1        # roll back one migration
```

`docker-compose.yml`'s `migrate` service runs `alembic upgrade head`
once and exits before `api`/`worker` start — a fresh `docker compose up`
always applies the current schema to a fresh Postgres volume.

### Test database strategy

Repository/lifecycle tests never touch a developer's personal database
or require Docker: `tests/conftest.py`'s `analysis_app_factory`
continues to override `get_analysis_repository`/`get_spatial_repository`
with the in-memory implementations, exactly as before F5. Dedicated
Postgres-repository tests (`test_postgres_repositories.py`) use an
isolated, file-less **SQLite** database per test (`sqlite:///:memory:`,
via `app.db.session.create_all_tables` — schema created directly from
ORM metadata, not through Alembic) — fast, hermetic, and dialect-close
enough to exercise the real repository code paths (JSON columns,
foreign keys, relationships) without requiring a running PostgreSQL
server for every `pytest -q` invocation. `alembic upgrade head` against
a *real* Postgres is exercised manually (`docker compose up`) — see
"Local development," below — not on every test run.

## Repository layer

`AnalysisRepository`/`SpatialRepository` stay Protocol-typed exactly as
F1-F4 defined them. Production `app/api/deps.py` now constructs
`PostgresAnalysisRepository`/`PostgresSpatialRepository` by default
(previously module-level `InMemory*` singletons); every test overrides
them unconditionally, so no existing test needed to change to keep
passing. `increment_attempt_count()` is the one new repository method
(both implementations), used by the worker for retry observability.

## Object storage

`app.services.file_storage.FileStorage` *is* the "ObjectStorage"
abstraction F5 asks for — `save`/`load` (kept, not renamed to `put`/
`get`, to avoid a needless rename of every existing call site) plus new
`exists`/`delete` methods. `LocalObjectStorage` is a documented public
alias for `LocalFileStorage` (the same class, two names) — a real S3/R2/
GCS-backed implementation can be added later without touching
`AnalysisService`/`AnalysisProcessingService`/the API layer, exactly the
guarantee this module already made before F5.

`storage_name` is always a server-generated key (a UUID-derived
filename — see `AnalysisService.create_analysis`), never the client's
own filename used as a path — every implementation can trust it as an
opaque, single-path-segment object key. `LocalFileStorage` additionally
refuses to write/read outside its `base_dir` even if that guarantee
were ever violated (defense in depth, unchanged from F1-F4).

In Docker, `api` and `worker` are separate containers — a shared
`uploads-data` volume (see `docker-compose.yml`) is what lets the
worker read back an image the API container wrote.

## Queue / worker design

`app.services.job_queue.JobQueue` — `RedisJobQueue` (production, backed
by [RQ](https://python-rq.org/)) and `InMemoryJobQueue` (test-only,
processes synchronously in-process — see `tests/conftest.py`).

**Why RQ, not Celery**: RQ's entire API is `enqueue`/`Worker` over a
plain Redis list — no message-broker protocol, no separate scheduler/
beat process, nothing to configure beyond a Redis URL. Celery's
additional machinery (exchanges, routing, a scheduler) solves problems
this system doesn't have; adding it would violate the milestone's own
"do not add Celery solely because it is popular" guidance.

`RedisJobQueue.enqueue_analysis()` enqueues
`app.worker.tasks.process_analysis_job` **by import-string**, not a
direct Python import — this is what keeps the API process from ever
importing `app.worker.tasks` (which imports the real, CLIP-capable
`DamageModel` stack). Only the worker process resolves that string.

`app/worker/main.py` (`python -m app.worker.main`) is the worker
entrypoint: eagerly loads the real model once via the *exact same*
`get_building_localizer`/`get_damage_classifier`/`get_damage_model`
functions `app/api/deps.py` already defines (called as plain Python
functions, not through FastAPI's `Depends`), publishes the result to
Redis, then runs an RQ `Worker` loop. `app/worker/tasks.py::
process_analysis_job` is the actual per-job function: bumps
`attempt_count`, then calls `AnalysisProcessingService.process()`
unchanged.

## Analysis lifecycle

The existing coarse `AnalysisStatus` (`uploaded` → `queued` →
`processing` → `completed`/`failed`) is preserved unchanged — F5 does
not introduce parallel, finer-grained status values, since every
existing consumer (the frontend's polling hook, `DamageAnalysis`'s
response contract, every F1-F4 test) already depends on exactly these
five values. The finer stages the milestone brief lists
(preprocessing/inference/damage_analysis/risk_assessment/
intelligence_processing) are represented as **structured log events**
instead (`stage=worker_pickup`/`stage=worker_done`, plus
`AnalysisProcessingService`'s own existing per-outcome log lines) — real
observability without a breaking schema change. `AnalysisProcessingService.
process()`'s own terminal-state guard (`if record.status in (COMPLETED,
FAILED): return`) is the enforcement mechanism against an invalid
`completed → processing` transition — unchanged from F4, and it already
does exactly what this milestone asks for.

## Idempotency / retries

**Idempotency was already structurally guaranteed before F5** — this
milestone's job was to verify and extend it, not invent it from scratch:

- `AnalysisProcessingService.process()`'s terminal-state guard means a
  duplicate job for an already-`completed`/`failed` analysis is a no-op.
- Every repository write is **replace-, not append-semantics**
  (`save_result()` overwrites `buildings`, not accumulates) — re-running
  a job that got partway through (a worker crash after transitioning to
  `processing` but before saving a result) simply redoes the work and
  overwrites, never duplicates.
- `PostgresSpatialRepository`'s own buildings view is the same table
  `PostgresAnalysisRepository.save_result()` writes, in one place —
  there is no second place a duplicate row could appear.

**Retries**: `RedisJobQueue` configures RQ's `Retry(max=JOB_MAX_RETRIES)`
per job. This only ever matters for *infrastructure* failures — a close
reading of `AnalysisProcessingService.process()` shows every ML-domain
failure (`ModelNotAvailableError`, any other inference exception) is
already caught *inside* `process()` and converted into a terminal,
recorded `AnalysisFailure` — `process()` itself never raises for those,
so RQ never sees an exception to retry. What genuinely propagates
(un-guarded, by the method's own existing structure) is a repository/
file-storage call failing outright — a dropped database connection, for
example — exactly the class of *transient* failure retrying is
appropriate for. No new "is this retryable?" classification logic was
needed; F4's existing exception boundaries already drew the line
correctly.

`attempt_count` (new column, bumped once per job pickup) is
observability, not enforcement — `JOB_MAX_RETRIES`/RQ's own `Retry`
bound the actual retry count.

## Model lifecycle

```
STARTING → MODEL_LOADING → READY
                          ↘ FAILED
(MODEL_ENABLED=false) → UNAVAILABLE
```

Published by the worker (`app.services.worker_status.ModelStatusPublisher`)
to one Redis key, read by the API
(`app.services.worker_status.ModelStatusReader`) — the API process
**never** constructs a `DamageModel` merely to answer `GET
/api/v1/model/status`; that was F4's own documented cold-start problem,
now fixed. `ModelStatusService`'s public contract (`enabled`/`provider`/
`status`) is unchanged from F4; `lifecycle_state`/`error` are new,
additive fields.

If the worker's model load fails (e.g. no network on first run), the
worker publishes `FAILED` with a short, client-safe `error` string
(never a traceback or filesystem path) and continues running — queued
jobs then fail cleanly with `MODEL_LOAD_FAILURE` (F4's existing error
code), not a crashed worker process.

## Health / readiness

- **`GET /health`** — liveness only: "is the process alive?" Never
  touches PostgreSQL/Redis/the model — a database outage must never
  make an otherwise-fine process look dead and get killed for no reason.
- **`GET /ready`** (new) — readiness: real PostgreSQL connectivity
  (`SELECT 1`) and real Redis connectivity (`PING`) both gate
  `status="ready"`; model status is reported as a third check but never
  gates it — a request can be accepted while the model is still loading
  (or disabled); it fails honestly and explicitly once actually
  processed, exactly like any other structured failure. Returns `503`
  when not ready.

Both connection checks use a bounded 5-second timeout — an unreachable
database/Redis must fail fast and honestly, never hang the request
indefinitely.

## Configuration

New, environment-driven (`app/core/config.py`), every one validated:

| Setting | Default | Validated |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://sentinelai:sentinelai@localhost:5432/sentinelai` | non-empty scheme |
| `REDIS_URL` | `redis://localhost:6379/0` | `redis://`/`rediss://`/`unix://` prefix |
| `OBJECT_STORAGE_BACKEND` | `local` | closed enum (`local`) |
| `OBJECT_STORAGE_ROOT` | `storage/uploads` | — |
| `WORKER_CONCURRENCY` | `1` | `>= 1` |
| `JOB_MAX_RETRIES` | `2` | `>= 0` |

No secret is ever hardcoded; `docker-compose.yml` reads
`POSTGRES_PASSWORD`/etc. from the environment with a local-dev-only
default, exactly like `apps/api/.env.example`'s existing convention for
every other setting.

## Observability

Structured log lines carry `analysis_id` end-to-end:
`stage=worker_pickup attempt=N` when a job is picked up,
`stage=worker_done status=... duration_ms=...` when it finishes — plus
F4's own existing per-outcome log lines inside `AnalysisProcessingService.
process()` (`"Analysis %s failed: model unavailable"`, etc., already
carrying `analysis_id`). Never logs image bytes, secrets, or a full
exception traceback — server-side `logger.exception()` calls capture
diagnostics for operators; API/log-visible messages stay short and
client-safe, unchanged from F4's own established discipline.

## Security / resource hardening

Preserved unchanged from F4: upload size limit (`MAX_UPLOAD_SIZE_MB`),
image dimension limit (`MODEL_MAX_IMAGE_DIM`), MIME/content validation,
server-generated (never client-controlled) storage keys, path-traversal
refusal in `LocalFileStorage`. New in F5: bounded database/Redis
connection timeouts (never hang indefinitely), a bounded RQ job timeout
(600s — generous for a cold CLIP load, still bounded), bounded retries
(`JOB_MAX_RETRIES`), and a clean `503` (not a raw 500) when the queue
itself is unreachable at enqueue time.

## Docker

One image (`docker/api.Dockerfile`, `python:3.12-slim`, CPU-only PyTorch
wheels — no CUDA base image, matches the actual development machine),
two roles (`api`: `uvicorn app.main:app`; `worker`:
`python -m app.worker.main`) — never two builds that can drift apart.
`postgres`/`redis` are the standard official images. `migrate` is a
one-shot service (`alembic upgrade head`, then exits) that `api`/
`worker` wait on. See `docker/README.md` for the full service table and
`docker-compose.yml` for volumes (`postgres-data`, `redis-data`,
`uploads-data` — shared between `api`/`worker`, `model-cache` —
worker-only, persists the downloaded CLIP checkpoint across restarts).

## Local development

```bash
docker compose up --build
```

- API: http://localhost:8000 (docs at `/docs`)
- Readiness: http://localhost:8000/ready
- Model status: http://localhost:8000/api/v1/model/status
- Web: http://localhost:3000

Without Docker (existing F1-F4 workflow, still supported): run
PostgreSQL/Redis yourself (or point `DATABASE_URL` at a local SQLite
file for a database-free smoke test), `alembic upgrade head`, then in
separate terminals: `uvicorn app.main:app --reload` and
`python -m app.worker.main`.

```bash
cd apps/api
alembic upgrade head
.venv\Scripts\python.exe -m pytest -q   # never needs Postgres/Redis running
```

## Testing

Repository CRUD/transactions, object storage (put/get/delete/missing/
path-traversal), queue (enqueue, `InMemoryJobQueue` idempotent
processing), lifecycle (valid/invalid transitions, terminal-state
guard), model (eager worker load, status publish/read, load failure),
end-to-end analysis (upload → persisted → enqueued → processed →
retrievable), failures (each `AnalysisErrorCode`), idempotency (a
duplicate `process()` call never duplicates buildings), F3 compatibility
(a persisted F4/F5 result still reaches F3 with CRS intact), security
(oversized upload, path traversal, dimension limits) — see
`apps/api/README.md`, "Milestone F5," for the exact test file list. The
real CLIP model is never required for the default `pytest -q` run;
`test_ml_real_inference_integration.py` (F4) remains the one explicit,
separately-runnable test that exercises it for real.

## Known limitations

- **Not deployed anywhere** — Docker Compose is a *local* production-style
  stack, not a cloud deployment. No autoscaling, no high availability, no
  managed database/Redis, no TLS termination, no production SLA.
- **No authentication/authorization** — deliberately out of scope for
  F5 (see the milestone brief's own non-goals); anyone who can reach the
  API can upload/read analyses.
- **`WORKER_CONCURRENCY`** is currently informational — `docker-compose.yml`
  runs one worker process; scaling to more workers means running
  multiple `worker` service replicas (RQ supports this natively — each
  additional worker just connects to the same Redis queue), not
  implemented/tested as part of this milestone.
- **No dead-letter queue / manual-requeue UI** — a job that exhausts its
  retries stays in whatever terminal state `process()` last recorded
  (usually a structured `AnalysisFailure`); there is no separate
  "poison queue" inspection tool.
- **SQLite, not Postgres, backs the default test suite** — a real
  Postgres-specific behavior difference (locking semantics, some
  constraint enforcement details) could in principle pass in tests and
  fail against real Postgres; `docker compose up` + a manual smoke test
  is the check against that (see the F5 final report's "Real
  end-to-end test").
- **Object storage is local-filesystem only** — `LocalObjectStorage` is
  the only implementation; an S3/R2/GCS-backed one is a real (not yet
  built) future addition, per the interface's own design intent.

## Recommended F6

A cinematic 3D frontend redesign (already deferred by name in this
milestone's own brief); real object storage (S3-compatible); a
dead-letter/poison-queue view; authentication; multi-worker horizontal
scaling, tested; a real xBD-trained checkpoint (still not implemented,
per F4's own honesty disclosure); CI running the Docker Compose stack
end-to-end.

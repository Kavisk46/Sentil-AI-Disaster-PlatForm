"""Redis-backed channel for the worker's model lifecycle state
(Milestone F5).

This is the fix for F4's own documented cold-start problem: `GET
/api/v1/model/status` must be servable by the API process **without**
that process ever constructing or loading a real `DamageModel` (a
40-150 second CPU operation on first load — see `apps/api/README.md`,
"Milestone F4"). Instead, the worker (`app/worker/main.py`) loads the
model once at its own startup and publishes its lifecycle state here;
the API only ever reads it back.

One Redis key, `sentinelai:model:status`, holding one JSON document — no
new infrastructure beyond the Redis instance the job queue already
requires (`app.services.job_queue`).
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel
from redis import Redis

_REDIS_KEY = "sentinelai:model:status"


class ModelLifecycleState(StrEnum):
    """See `docs/architecture/production.md`, "Model lifecycle," for the
    full state diagram. `STARTING` is also the API's own honest fallback
    when nothing has been published yet (worker not started, or Redis
    unreachable) — never fabricated readiness."""

    STARTING = "STARTING"
    MODEL_LOADING = "MODEL_LOADING"
    READY = "READY"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class WorkerModelStatus(BaseModel):
    lifecycle_state: ModelLifecycleState
    enabled: bool
    provider: str
    model_name: str
    model_version: str
    model_loaded: bool
    device: str
    # A short, client-safe description only — never a raw traceback or a
    # filesystem path (see `docs/architecture/production.md`, "Security
    # hardening").
    error: str | None = None
    updated_at: datetime


class ModelStatusPublisher:
    """Worker-side only — the API process never constructs this."""

    def __init__(self, redis_url: str) -> None:
        self._redis = Redis.from_url(redis_url, socket_connect_timeout=5, socket_timeout=5)

    def publish(self, status: WorkerModelStatus) -> None:
        self._redis.set(_REDIS_KEY, status.model_dump_json())


class ModelStatusReader:
    """API-side only. `read()` never raises on a Redis outage — `/ready`
    and `/api/v1/model/status` must stay honest (report "not yet known")
    rather than 500 just because the status channel itself is down."""

    def __init__(self, redis_url: str) -> None:
        self._redis = Redis.from_url(redis_url, socket_connect_timeout=5, socket_timeout=5)

    def read(self) -> WorkerModelStatus | None:
        try:
            raw = self._redis.get(_REDIS_KEY)
        except Exception:
            return None
        if raw is None:
            return None
        return WorkerModelStatus.model_validate_json(raw)

    def ping(self) -> bool:
        try:
            return bool(self._redis.ping())
        except Exception:
            return False

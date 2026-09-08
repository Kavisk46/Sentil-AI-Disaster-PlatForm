"""Background job queue abstraction (Milestone F5).

Replaces FastAPI `BackgroundTasks` (Milestone 4's original mechanism —
`process()` ran in-process, in the same request's thread pool, right
after the response was sent) with a real, durable, cross-process queue:
the API process only ever *enqueues*; a separate worker process
(`app/worker/`) dequeues and actually runs `AnalysisProcessingService.
process()`. This is the architectural fix for F4's own documented
limitation — the API process must never block on (or even import) the
CLIP model loading/inference path.

`RedisJobQueue` is production; `InMemoryJobQueue` is test-only — see
`tests/conftest.py`, which wires it to call `AnalysisProcessingService.
process()` synchronously and in-process, exactly reproducing
`BackgroundTasks`' old test-time behavior (a `TestClient` POST completes
processing before the response object is inspected) with no real Redis
or worker process required. Production DI (`app/api/deps.py`) never
constructs `InMemoryJobQueue`.
"""

from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from redis import Redis
from rq import Queue
from rq.job import Retry

# The worker looks this exact dotted path up by import string (see
# app/worker/tasks.py) — RQ's own recommended pattern for decoupling the
# *enqueuing* process (this one) from the process that must actually be
# able to import and run the job (the worker). The API process importing
# this module never imports `app.worker.tasks` (which imports the real
# `DamageModel`/CLIP stack) — only this string constant does, at enqueue
# time, resolved by the *worker*, never here.
_PROCESS_ANALYSIS_JOB_PATH = "app.worker.tasks.process_analysis_job"
_QUEUE_NAME = "analysis"


class JobQueue(Protocol):
    def enqueue_analysis(self, analysis_id: UUID) -> None:
        """Schedule `analysis_id` for background processing.

        Must be safe to call more than once for the same id (see
        `docs/architecture/production.md`, "Idempotency") — the eventual
        worker-side processing is itself idempotent
        (`AnalysisProcessingService.process()`'s existing terminal-state
        guard, plus every repository's replace- not append-semantics), so
        this method never needs to detect or reject a duplicate itself.
        """
        ...


class RedisJobQueue:
    """Enqueues onto a Redis-backed RQ queue. `job_id` is the stable
    string `f"analysis:{analysis_id}"` — not a deduplication mechanism in
    itself (RQ's own job registry semantics around a reused id are an
    implementation detail this code doesn't rely on), but it does make
    every job for a given analysis independently identifiable in Redis/
    the RQ dashboard, which is the actually useful property for
    observability.
    """

    def __init__(self, redis_url: str, *, max_retries: int) -> None:
        self._redis = Redis.from_url(redis_url, socket_connect_timeout=5, socket_timeout=5)
        self._queue: Queue = Queue(_QUEUE_NAME, connection=self._redis)
        self._max_retries = max_retries

    def enqueue_analysis(self, analysis_id: UUID) -> None:
        self._queue.enqueue(
            _PROCESS_ANALYSIS_JOB_PATH,
            str(analysis_id),
            job_id=f"analysis:{analysis_id}",
            retry=Retry(max=self._max_retries),
            # A job hung on a wedged CLIP forward pass must not block the
            # queue forever — see "Resource / security hardening" in
            # docs/architecture/production.md. Generous (CLIP's own cold
            # first-load can take 40-150s — see apps/api/README.md,
            # "Milestone F4") but still bounded.
            job_timeout=600,
        )

    def ping(self) -> bool:
        """Used by `GET /ready` — a real, cheap Redis round trip, never a
        fabricated "yes"."""
        try:
            return bool(self._redis.ping())
        except Exception:
            return False


class InMemoryJobQueue:
    """Test-only synchronous stand-in — see module docstring. `enqueued`
    records every id passed to `enqueue_analysis`, in order, so a test can
    assert on it directly without needing a real queue backend."""

    def __init__(self, processor: Callable[[UUID], None]) -> None:
        self._processor = processor
        self.enqueued: list[UUID] = []

    def enqueue_analysis(self, analysis_id: UUID) -> None:
        self.enqueued.append(analysis_id)
        self._processor(analysis_id)

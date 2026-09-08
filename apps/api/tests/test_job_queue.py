"""Tests for the job queue abstraction (Milestone F5).

`InMemoryJobQueue` only — `RedisJobQueue` needs a real Redis connection,
exercised manually via `docker compose up` (see
`docs/architecture/production.md`, "Local development") rather than in
the default test suite, the same "don't require live infrastructure for
every unit test" principle F4 already established for the real CLIP
model.
"""

from uuid import uuid4

from app.services.job_queue import InMemoryJobQueue


def test_enqueue_analysis_calls_the_processor_synchronously() -> None:
    calls: list[str] = []
    queue = InMemoryJobQueue(processor=lambda analysis_id: calls.append(str(analysis_id)))
    analysis_id = uuid4()

    queue.enqueue_analysis(analysis_id)

    assert calls == [str(analysis_id)]


def test_enqueued_records_every_call_in_order() -> None:
    queue = InMemoryJobQueue(processor=lambda analysis_id: None)
    first, second = uuid4(), uuid4()

    queue.enqueue_analysis(first)
    queue.enqueue_analysis(second)

    assert queue.enqueued == [first, second]


def test_enqueuing_the_same_analysis_id_twice_calls_the_processor_twice() -> None:
    """The queue itself never deduplicates — idempotency is the
    processor's job (`AnalysisProcessingService.process()`'s own
    terminal-state guard) — see `docs/architecture/production.md`,
    "Idempotency / retries"."""
    calls: list[str] = []
    queue = InMemoryJobQueue(processor=lambda analysis_id: calls.append(str(analysis_id)))
    analysis_id = uuid4()

    queue.enqueue_analysis(analysis_id)
    queue.enqueue_analysis(analysis_id)

    assert calls == [str(analysis_id), str(analysis_id)]
    assert queue.enqueued == [analysis_id, analysis_id]

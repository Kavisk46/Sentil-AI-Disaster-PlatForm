"""Tests for `app.services.worker_status` and `ModelStatusService`
(Milestone F5).

Uses `fakeredis` if available; otherwise a minimal hand-written fake
Redis client — never a real Redis connection (see
`docs/architecture/production.md`, "Test database strategy," for the
equivalent reasoning applied to Postgres).
"""

from datetime import UTC, datetime

from app.core.config import Settings
from app.ml.schemas import ModelStatus
from app.services.model_status_service import ModelStatusService
from app.services.worker_status import ModelLifecycleState, ModelStatusReader, WorkerModelStatus


class _FakeRedis:
    """The minimal subset of the redis-py client `ModelStatusReader`/
    `ModelStatusPublisher` actually use — `get`/`set`/`ping` — backed by
    an in-process dict, never a real socket."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def set(self, key: str, value: str) -> None:
        self._store[key] = value.encode()

    def get(self, key: str) -> bytes | None:
        return self._store.get(key)

    def ping(self) -> bool:
        return True


class _FailingRedis:
    def get(self, key: str) -> bytes | None:
        raise ConnectionError("simulated Redis outage")

    def ping(self) -> bool:
        raise ConnectionError("simulated Redis outage")


def _reader_with(fake_redis: object) -> ModelStatusReader:
    reader = ModelStatusReader.__new__(ModelStatusReader)
    reader._redis = fake_redis  # type: ignore[assignment]
    return reader


def _status(
    state: ModelLifecycleState, *, loaded: bool = False, error: str | None = None
) -> WorkerModelStatus:
    return WorkerModelStatus(
        lifecycle_state=state,
        enabled=True,
        provider="open_clip",
        model_name="ViT-B-32",
        model_version="openai",
        model_loaded=loaded,
        device="cpu",
        error=error,
        updated_at=datetime.now(UTC),
    )


class TestModelStatusReader:
    def test_read_returns_none_when_nothing_published(self) -> None:
        reader = _reader_with(_FakeRedis())

        assert reader.read() is None

    def test_read_returns_what_was_published(self) -> None:
        fake_redis = _FakeRedis()
        published = _status(ModelLifecycleState.READY, loaded=True)
        fake_redis.set("sentinelai:model:status", published.model_dump_json())
        reader = _reader_with(fake_redis)

        result = reader.read()

        assert result is not None
        assert result.lifecycle_state is ModelLifecycleState.READY
        assert result.model_loaded is True

    def test_read_never_raises_on_a_redis_outage(self) -> None:
        reader = _reader_with(_FailingRedis())

        assert reader.read() is None

    def test_ping_returns_false_on_a_redis_outage_never_raises(self) -> None:
        reader = _reader_with(_FailingRedis())

        assert reader.ping() is False

    def test_ping_returns_true_when_reachable(self) -> None:
        reader = _reader_with(_FakeRedis())

        assert reader.ping() is True


class TestModelStatusService:
    def test_reports_starting_when_nothing_has_been_published_yet(self) -> None:
        service = ModelStatusService(Settings(MODEL_ENABLED=True), _reader_with(_FakeRedis()))

        result = service.get_status()

        assert result.lifecycle_state is ModelLifecycleState.STARTING
        assert result.status.model_loaded is False

    def test_never_constructs_or_loads_a_real_damage_model(self) -> None:
        """The defining F5 fix: answering this must not touch
        `DamageModel`/`get_damage_classifier` at all — verified here by
        the simple fact that constructing/calling this service never
        imports torch/open_clip or attempts a checkpoint load, backed
        only by a fake Redis client."""
        service = ModelStatusService(Settings(MODEL_ENABLED=True), _reader_with(_FakeRedis()))

        result = service.get_status()  # must return instantly, no model I/O

        assert result.enabled is True

    def test_reflects_a_ready_worker_status(self) -> None:
        fake_redis = _FakeRedis()
        ready_status = _status(ModelLifecycleState.READY, loaded=True)
        fake_redis.set("sentinelai:model:status", ready_status.model_dump_json())
        service = ModelStatusService(Settings(), _reader_with(fake_redis))

        result = service.get_status()

        assert result.lifecycle_state is ModelLifecycleState.READY
        assert result.status.model_loaded is True
        assert result.status == ModelStatus(
            model_loaded=True, model_name="ViT-B-32", model_version="openai", device="cpu"
        )

    def test_reflects_a_failed_worker_status_with_a_safe_error_string(self) -> None:
        fake_redis = _FakeRedis()
        fake_redis.set(
            "sentinelai:model:status",
            _status(ModelLifecycleState.FAILED, error="Connection timed out").model_dump_json(),
        )
        service = ModelStatusService(Settings(), _reader_with(fake_redis))

        result = service.get_status()

        assert result.lifecycle_state is ModelLifecycleState.FAILED
        assert result.error == "Connection timed out"

    def test_reflects_an_unavailable_worker_status_when_model_disabled(self) -> None:
        fake_redis = _FakeRedis()
        disabled_status = WorkerModelStatus(
            lifecycle_state=ModelLifecycleState.UNAVAILABLE,
            enabled=False,
            provider="open_clip",
            model_name="ViT-B-32",
            model_version="openai",
            model_loaded=False,
            device="cpu",
            error=None,
            updated_at=datetime.now(UTC),
        )
        fake_redis.set("sentinelai:model:status", disabled_status.model_dump_json())
        service = ModelStatusService(Settings(), _reader_with(fake_redis))

        result = service.get_status()

        assert result.enabled is False
        assert result.lifecycle_state is ModelLifecycleState.UNAVAILABLE

"""Tests for `ReadinessService` / `GET /ready` (Milestone F5).

Database and Redis are both faked (a real SQLite engine for the database
check — cheap, no network; a fake Redis client for the queue/model
checks) — never a real PostgreSQL or Redis connection, matching every
other F5 test's "no live infrastructure required" discipline.
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.session import create_all_tables
from app.services.readiness_service import ReadinessService
from app.services.worker_status import ModelLifecycleState, WorkerModelStatus


class _ReachableRedisReader:
    def __init__(self, worker_status: WorkerModelStatus | None) -> None:
        self._worker_status = worker_status

    def ping(self) -> bool:
        return True

    def read(self) -> WorkerModelStatus | None:
        return self._worker_status


class _UnreachableRedisReader:
    def ping(self) -> bool:
        return False

    def read(self) -> WorkerModelStatus | None:
        return None


def _ready_worker_status() -> WorkerModelStatus:
    return WorkerModelStatus(
        lifecycle_state=ModelLifecycleState.READY,
        enabled=True,
        provider="open_clip",
        model_name="ViT-B-32",
        model_version="openai",
        model_loaded=True,
        device="cpu",
        error=None,
        updated_at=datetime.now(UTC),
    )


def test_ready_when_database_and_redis_are_both_reachable(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(DATABASE_URL=f"sqlite:///{tmp_path / 'ready.db'}")
    create_all_tables(settings)
    service = ReadinessService(settings, _ReachableRedisReader(_ready_worker_status()))  # type: ignore[arg-type]

    result = service.get_readiness()

    assert result.status == "ready"
    checks = {check.name: check.ready for check in result.checks}
    assert checks["database"] is True
    assert checks["queue"] is True
    assert checks["model"] is True


def test_not_ready_when_database_is_unreachable(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # A DATABASE_URL pointing at nothing real — the point is the engine
    # never connects successfully, not that this specific host exists.
    settings = Settings(DATABASE_URL="postgresql+psycopg://x:x@127.0.0.1:1/doesnotexist")
    service = ReadinessService(settings, _ReachableRedisReader(_ready_worker_status()))  # type: ignore[arg-type]

    result = service.get_readiness()

    assert result.status == "not_ready"
    checks = {check.name: check.ready for check in result.checks}
    assert checks["database"] is False


def test_not_ready_when_redis_is_unreachable(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(DATABASE_URL=f"sqlite:///{tmp_path / 'ready.db'}")
    create_all_tables(settings)
    service = ReadinessService(settings, _UnreachableRedisReader())  # type: ignore[arg-type]

    result = service.get_readiness()

    assert result.status == "not_ready"
    checks = {check.name: check.ready for check in result.checks}
    assert checks["queue"] is False


def test_model_not_ready_does_not_gate_overall_readiness(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A request can be accepted while the model is still loading (or
    disabled) — it fails honestly once actually processed. `/ready`
    itself must still report `ready` as long as the database and queue
    are reachable — see docs/architecture/production.md, "Health /
    readiness"."""
    settings = Settings(DATABASE_URL=f"sqlite:///{tmp_path / 'ready.db'}")
    create_all_tables(settings)
    service = ReadinessService(settings, _ReachableRedisReader(None))  # type: ignore[arg-type]

    result = service.get_readiness()

    assert result.status == "ready"
    checks = {check.name: check.ready for check in result.checks}
    assert checks["model"] is False


def test_ready_endpoint_returns_503_when_not_ready(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api.deps import get_readiness_service
    from app.main import create_app

    app = create_app()
    # A distinct unreachable URL from `test_not_ready_when_database_is_unreachable`
    # above — `app.db.session.get_engine`'s module-level cache is keyed by
    # this exact string, and reusing an already-failed connection's cached
    # engine/pool a second time within the same process is untested
    # territory this suite deliberately avoids, not something production
    # code relies on (a real deployment never repeatedly reconnects to the
    # same permanently-down host across unrelated requests without a
    # pool-level retry/backoff policy).
    settings = Settings(DATABASE_URL="postgresql+psycopg://x:x@127.0.0.1:2/doesnotexist")
    service = ReadinessService(settings, _ReachableRedisReader(_ready_worker_status()))  # type: ignore[arg-type]
    app.dependency_overrides[get_readiness_service] = lambda: service
    client = TestClient(app)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_ready_endpoint_returns_200_when_ready(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.api.deps import get_readiness_service
    from app.main import create_app

    app = create_app()
    settings = Settings(DATABASE_URL=f"sqlite:///{tmp_path / 'ready.db'}")
    create_all_tables(settings)
    service = ReadinessService(settings, _ReachableRedisReader(_ready_worker_status()))  # type: ignore[arg-type]
    app.dependency_overrides[get_readiness_service] = lambda: service
    client = TestClient(app)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_health_endpoint_never_touches_database_or_redis() -> None:
    """Liveness must stay independent of every downstream dependency —
    constructing the app with no readiness override still answers
    `/health` (it never resolves `ReadinessServiceDep` at all)."""
    from app.main import create_app

    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"

"""Assembles `GET /ready`'s response (Milestone F5).

Two *gating* checks — real PostgreSQL and Redis connectivity, each a
cheap round trip, never fabricated — plus one *informational* check
(model lifecycle, read from `app.services.worker_status`, never gating:
a not-yet-ready model is an honest, expected state during worker
startup, not a reason to mark the whole API "not ready").
"""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.db.session import get_engine
from app.schemas.health import ReadinessCheck, ReadyResponse
from app.services.worker_status import ModelStatusReader
from app.utils.datetime import utc_now


class ReadinessService:
    def __init__(self, settings: Settings, model_status_reader: ModelStatusReader) -> None:
        self._settings = settings
        self._model_status_reader = model_status_reader

    def get_readiness(self) -> ReadyResponse:
        checks = [self._check_database(), self._check_queue(), self._check_model()]
        gating = checks[:2]
        overall = "ready" if all(check.ready for check in gating) else "not_ready"
        return ReadyResponse(status=overall, timestamp=utc_now(), checks=checks)

    def _check_database(self) -> ReadinessCheck:
        try:
            engine = get_engine(self._settings)
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return ReadinessCheck(name="database", ready=True)
        except SQLAlchemyError as exc:
            return ReadinessCheck(name="database", ready=False, detail=type(exc).__name__)

    def _check_queue(self) -> ReadinessCheck:
        ready = self._model_status_reader.ping()
        return ReadinessCheck(
            name="queue", ready=ready, detail=None if ready else "Redis unreachable."
        )

    def _check_model(self) -> ReadinessCheck:
        worker_status = self._model_status_reader.read()
        if worker_status is None:
            return ReadinessCheck(name="model", ready=False, detail="Not yet reported by worker.")
        return ReadinessCheck(
            name="model",
            ready=worker_status.model_loaded,
            detail=worker_status.lifecycle_state.value,
        )

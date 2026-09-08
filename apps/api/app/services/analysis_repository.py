"""Analysis metadata storage.

Behind a small repository interface (`AnalysisRepository`) rather than a
dict exposed directly, so a PostgreSQL-backed implementation can replace
`InMemoryAnalysisRepository` in a later milestone without changing
`AnalysisService`, `AnalysisProcessingService`, or any route — see
PROJECT_ROADMAP.md.

As of Milestone 4, this module imports from `app.ml.schemas` — the
repository now persists ML results (`DamageSummary`, `BuildingDamage`,
`ModelStatus`), and the task's own requirement not to duplicate
`DamageAnalysis`/its parts means storing the *real* ML types here rather
than parallel ones. This mirrors the already-existing reverse coupling
(`app.ml.schemas` importing `app.schemas.analysis.AnalysisStatus`), not a
new kind of dependency direction in this codebase.
"""

import threading
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from app.ml.schemas import BuildingDamage, DamageSummary, ModelStatus
from app.schemas.analysis import AnalysisFailure, AnalysisStatus


class AnalysisNotFoundError(Exception):
    """Raised when `analysis_id` doesn't correspond to any known analysis.

    Raised by the mutating repository methods (`update_status`,
    `save_result`, `save_failure`) — by the time those run, the id is
    expected to already exist (it was created earlier in the same
    request/background-task flow), so a miss here signals a genuine bug,
    not a normal "not found" the caller should quietly handle. `GET
    /api/v1/analysis/{analysis_id}` maps this to `404` — see
    `app/api/exception_handlers.py`.
    """

    def __init__(self, analysis_id: UUID) -> None:
        self.analysis_id = analysis_id
        super().__init__(f"No analysis found with id {analysis_id}.")


@dataclass(frozen=True, slots=True)
class AnalysisRecord:
    """Server-side metadata for one uploaded analysis.

    Never returned as-is over the API — `storage_name` in particular is a
    filesystem implementation detail. See `AnalysisCreateResponse` for the
    upload contract and `app.ml.schemas.DamageAnalysis` (assembled from
    this record by `AnalysisProcessingService.get_analysis`) for the
    result contract.

    Immutable by design (`frozen=True`): every state transition
    (`update_status`/`save_result`/`save_failure`) replaces the stored
    record with a new one via `dataclasses.replace`, rather than mutating
    fields in place — simpler to reason about under the repository's
    lock, and there is exactly one place (`InMemoryAnalysisRepository`)
    where that replacement happens.
    """

    analysis_id: UUID
    status: AnalysisStatus
    original_filename: str
    storage_name: str
    content_type: str
    size_bytes: int
    created_at: datetime
    updated_at: datetime
    summary: DamageSummary | None = None
    buildings: tuple[BuildingDamage, ...] | None = None
    model_metadata: ModelStatus | None = None
    failure: AnalysisFailure | None = None
    # Milestone F5: how many times a worker has attempted to process this
    # analysis — see `increment_attempt_count` below. Always `0` for a
    # record that has never been picked up by a worker yet.
    attempt_count: int = 0


class AnalysisRepository(Protocol):
    def create(self, record: AnalysisRecord) -> None: ...
    def get(self, analysis_id: UUID) -> AnalysisRecord | None: ...

    def update_status(self, analysis_id: UUID, status: AnalysisStatus) -> AnalysisRecord:
        """Transition `analysis_id` to `status`, touching `updated_at`.

        Raises `AnalysisNotFoundError` if `analysis_id` is unknown.
        """
        ...

    def save_result(
        self,
        analysis_id: UUID,
        *,
        summary: DamageSummary,
        buildings: Sequence[BuildingDamage],
        model_metadata: ModelStatus,
    ) -> AnalysisRecord:
        """Atomically set `status=COMPLETED` and attach a real result.

        Raises `AnalysisNotFoundError` if `analysis_id` is unknown.
        """
        ...

    def save_failure(self, analysis_id: UUID, failure: AnalysisFailure) -> AnalysisRecord:
        """Atomically set `status=FAILED` and attach a structured reason.

        Raises `AnalysisNotFoundError` if `analysis_id` is unknown.
        """
        ...

    def increment_attempt_count(self, analysis_id: UUID) -> int:
        """Milestone F5: record one more worker attempt at processing
        `analysis_id`; returns the new count. Raises
        `AnalysisNotFoundError` if `analysis_id` is unknown."""
        ...


class InMemoryAnalysisRepository:
    """Process-local, non-persistent store.

    Fine for local development and tests; records vanish on restart. A
    single instance must be shared across requests within a process (see
    `app/api/deps.py`) — a fresh instance per request would forget every
    analysis immediately after creating it. The lock also makes this safe
    to call from a FastAPI background task running on a different thread
    than the request that scheduled it (see
    `app/services/analysis_processing_service.py`).
    """

    def __init__(self) -> None:
        self._records: dict[UUID, AnalysisRecord] = {}
        self._lock = threading.Lock()

    def create(self, record: AnalysisRecord) -> None:
        with self._lock:
            self._records[record.analysis_id] = record

    def get(self, analysis_id: UUID) -> AnalysisRecord | None:
        with self._lock:
            return self._records.get(analysis_id)

    def update_status(self, analysis_id: UUID, status: AnalysisStatus) -> AnalysisRecord:
        return self._replace(analysis_id, status=status)

    def save_result(
        self,
        analysis_id: UUID,
        *,
        summary: DamageSummary,
        buildings: Sequence[BuildingDamage],
        model_metadata: ModelStatus,
    ) -> AnalysisRecord:
        return self._replace(
            analysis_id,
            status=AnalysisStatus.COMPLETED,
            summary=summary,
            buildings=tuple(buildings),
            model_metadata=model_metadata,
        )

    def save_failure(self, analysis_id: UUID, failure: AnalysisFailure) -> AnalysisRecord:
        return self._replace(analysis_id, status=AnalysisStatus.FAILED, failure=failure)

    def increment_attempt_count(self, analysis_id: UUID) -> int:
        with self._lock:
            existing = self._records.get(analysis_id)
            if existing is None:
                raise AnalysisNotFoundError(analysis_id)
            updated = replace(
                existing, attempt_count=existing.attempt_count + 1, updated_at=datetime.now(UTC)
            )
            self._records[analysis_id] = updated
            return updated.attempt_count

    def _replace(self, analysis_id: UUID, **changes: object) -> AnalysisRecord:
        with self._lock:
            existing = self._records.get(analysis_id)
            if existing is None:
                raise AnalysisNotFoundError(analysis_id)
            updated = replace(existing, updated_at=datetime.now(UTC), **changes)  # type: ignore[arg-type]
            self._records[analysis_id] = updated
            return updated

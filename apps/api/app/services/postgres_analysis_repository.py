"""PostgreSQL-backed `AnalysisRepository` (Milestone F5).

Implements the exact same `AnalysisRepository` Protocol
(`app/services/analysis_repository.py`) `InMemoryAnalysisRepository`
does — production DI (`app/api/deps.py`) swaps to this implementation;
nothing in `AnalysisService`/`AnalysisProcessingService`/the API layer
changes. Domain objects in, domain objects out: this is the only module
that imports `app.db.models`, translating to/from `AnalysisRecord`
(`app.ml.schemas`) at every boundary — no ORM object ever leaks past
this file.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AnalysisORM, BuildingDamageORM
from app.ml.schemas import BuildingDamage, DamageSummary, ModelStatus
from app.schemas.analysis import AnalysisErrorCode, AnalysisFailure, AnalysisStatus
from app.services.analysis_repository import AnalysisNotFoundError, AnalysisRecord


def _as_utc(value: datetime) -> datetime:
    """Every timestamp this codebase writes is `datetime.now(UTC)`
    (timezone-aware) — but SQLite (used by the test suite's isolated
    databases, see `tests/test_postgres_repositories.py`) has no native
    timezone-aware storage and silently returns a *naive* `datetime` on
    read regardless of the column's `DateTime(timezone=True)` type. Real
    PostgreSQL preserves tzinfo correctly, so this is a no-op there —
    defensive, dialect-agnostic correctness, not a workaround for a bug
    in this codebase's own writes."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _to_record(row: AnalysisORM) -> AnalysisRecord:
    return AnalysisRecord(
        analysis_id=row.analysis_id,
        status=AnalysisStatus(row.status),
        original_filename=row.original_filename,
        storage_name=row.storage_name,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
        attempt_count=row.attempt_count,
        summary=DamageSummary.model_validate(row.summary) if row.summary is not None else None,
        buildings=tuple(to_building(b) for b in row.buildings) if row.buildings else None,
        model_metadata=(
            ModelStatus.model_validate(row.model_metadata)
            if row.model_metadata is not None
            else None
        ),
        failure=(
            AnalysisFailure(
                code=AnalysisErrorCode(row.failure_code), message=row.failure_message or ""
            )
            if row.failure_code is not None
            else None
        ),
    )


def to_building(row: BuildingDamageORM) -> BuildingDamage:
    return BuildingDamage.model_validate(
        {
            "building_id": row.building_id,
            "damage_class": row.damage_class,
            "confidence": row.confidence,
            "bounding_box": row.bounding_box,
            "geometry": row.geometry,
            "coordinate_reference_system": row.coordinate_reference_system,
            "georeferenced": row.georeferenced,
        }
    )


def _building_to_orm(analysis_id: UUID, building: BuildingDamage) -> BuildingDamageORM:
    return BuildingDamageORM(
        analysis_id=analysis_id,
        building_id=building.building_id,
        damage_class=building.damage_class.value,
        confidence=building.confidence,
        bounding_box=(
            None
            if building.bounding_box is None
            else {
                "x_min": building.bounding_box.x_min,
                "y_min": building.bounding_box.y_min,
                "x_max": building.bounding_box.x_max,
                "y_max": building.bounding_box.y_max,
            }
        ),
        geometry=(None if building.geometry is None else building.geometry.model_dump()),
        coordinate_reference_system=building.coordinate_reference_system.value,
        georeferenced=building.georeferenced,
    )


class PostgresAnalysisRepository:
    """A new `Session` is opened per call via `session_factory` — this
    repository is a thin, stateless adapter, never holding a session open
    across calls (unlike `InMemoryAnalysisRepository`'s dict, which *is*
    the state). Safe to share one instance across every request: FastAPI
    already gives each request its own transaction via each method's own
    `with self._session_factory() as session:` block.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create(self, record: AnalysisRecord) -> None:
        with self._session_factory() as session:
            session.add(
                AnalysisORM(
                    analysis_id=record.analysis_id,
                    status=record.status.value,
                    original_filename=record.original_filename,
                    storage_name=record.storage_name,
                    content_type=record.content_type,
                    size_bytes=record.size_bytes,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                    attempt_count=0,
                )
            )
            session.commit()

    def get(self, analysis_id: UUID) -> AnalysisRecord | None:
        with self._session_factory() as session:
            row = session.get(AnalysisORM, analysis_id)
            return _to_record(row) if row is not None else None

    def update_status(self, analysis_id: UUID, status: AnalysisStatus) -> AnalysisRecord:
        with self._session_factory() as session:
            row = self._get_or_raise(session, analysis_id)
            row.status = status.value
            row.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
            return _to_record(row)

    def save_result(
        self,
        analysis_id: UUID,
        *,
        summary: DamageSummary,
        buildings: Sequence[BuildingDamage],
        model_metadata: ModelStatus,
    ) -> AnalysisRecord:
        with self._session_factory() as session:
            row = self._get_or_raise(session, analysis_id)
            row.status = AnalysisStatus.COMPLETED.value
            row.summary = summary.model_dump(mode="json")
            row.model_metadata = model_metadata.model_dump(mode="json")
            row.updated_at = datetime.now(UTC)
            # Replace-semantics, not append: re-running a job (a retry, or
            # a duplicate delivery) for the same analysis_id overwrites
            # its buildings rather than accumulating duplicates — the
            # same idempotency guarantee `InMemorySpatialRepository.
            # save_buildings` already gives (`self._buildings[analysis_id]
            # = tuple(buildings)`, not an append).
            row.buildings.clear()
            for building in buildings:
                row.buildings.append(_building_to_orm(analysis_id, building))
            session.commit()
            session.refresh(row)
            return _to_record(row)

    def save_failure(self, analysis_id: UUID, failure: AnalysisFailure) -> AnalysisRecord:
        with self._session_factory() as session:
            row = self._get_or_raise(session, analysis_id)
            row.status = AnalysisStatus.FAILED.value
            row.failure_code = failure.code.value
            row.failure_message = failure.message
            row.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
            return _to_record(row)

    def increment_attempt_count(self, analysis_id: UUID) -> int:
        """Milestone F5: bumped once per worker job attempt, before
        `AnalysisProcessingService.process()` runs — see
        `app/worker/tasks.py`. Returns the new count so the caller can log
        it without a second round trip."""
        with self._session_factory() as session:
            row = self._get_or_raise(session, analysis_id)
            row.attempt_count += 1
            row.updated_at = datetime.now(UTC)
            session.commit()
            return row.attempt_count

    @staticmethod
    def _get_or_raise(session: Session, analysis_id: UUID) -> AnalysisORM:
        row = session.get(AnalysisORM, analysis_id)
        if row is None:
            raise AnalysisNotFoundError(analysis_id)
        return row


def all_analysis_ids(session_factory: sessionmaker[Session]) -> list[UUID]:
    """Diagnostic helper (used by tests only) — every persisted analysis
    id, oldest first."""
    with session_factory() as session:
        rows = session.execute(select(AnalysisORM.analysis_id).order_by(AnalysisORM.created_at))
        return [row[0] for row in rows]

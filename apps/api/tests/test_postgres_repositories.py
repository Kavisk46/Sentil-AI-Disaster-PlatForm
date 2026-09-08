"""PostgreSQL-backed repository tests (Milestone F5).

Uses an isolated, in-memory SQLite database per test (via
`app.db.session.create_all_tables`) — never a developer's personal
database, never Docker, never network I/O. Close enough to real
PostgreSQL to exercise the actual repository code paths (JSON columns,
foreign keys, relationships, transactions) — see
`docs/architecture/production.md`, "Test database strategy," for why
this is deliberately not a real-Postgres-required test, and
`test_analysis_lifecycle.py`'s own "no real database" precedent for the
in-memory repository's equivalent tests.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.db.session import create_all_tables, get_session_factory
from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.ml.geospatial.geometry import BoundingBoxGeometry, PointGeometry
from app.ml.schemas import BuildingDamage, DamageClass, DamageSummary, ModelStatus
from app.schemas.analysis import AnalysisErrorCode, AnalysisFailure, AnalysisStatus
from app.services.analysis_repository import AnalysisNotFoundError, AnalysisRecord
from app.services.postgres_analysis_repository import PostgresAnalysisRepository
from app.services.postgres_spatial_repository import PostgresSpatialRepository


@pytest.fixture
def settings(tmp_path) -> Settings:  # type: ignore[no-untyped-def]
    # A distinct SQLite file per test (not a single shared `:memory:` URL)
    # so `get_engine`/`get_session_factory`'s module-level cache (keyed by
    # DATABASE_URL) never leaks state between tests. Schema creation
    # happens here, not in an individual repository fixture, so every
    # test in this module gets a real, queryable schema regardless of
    # which repository fixture(s) it actually requests.
    db_path = tmp_path / "test.db"
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    create_all_tables(settings)
    return settings


@pytest.fixture
def repository(settings: Settings) -> PostgresAnalysisRepository:
    return PostgresAnalysisRepository(get_session_factory(settings))


@pytest.fixture
def spatial_repository(settings: Settings) -> PostgresSpatialRepository:
    return PostgresSpatialRepository(get_session_factory(settings))


def _record(analysis_id=None, status: AnalysisStatus = AnalysisStatus.UPLOADED) -> AnalysisRecord:
    now = datetime.now(UTC)
    return AnalysisRecord(
        analysis_id=analysis_id or uuid4(),
        status=status,
        original_filename="aerial.png",
        storage_name=f"{uuid4()}.png",
        content_type="image/png",
        size_bytes=1024,
        created_at=now,
        updated_at=now,
    )


def _building(
    building_id: str,
    damage_class: DamageClass,
    confidence: float = 0.9,
    geometry: PointGeometry | None = None,
    crs: CoordinateReferenceSystem = CoordinateReferenceSystem.WGS84,
    georeferenced: bool = True,
) -> BuildingDamage:
    return BuildingDamage(
        building_id=building_id,
        damage_class=damage_class,
        confidence=confidence,
        geometry=geometry or PointGeometry(coordinates=(20.0, 10.0)),
        coordinate_reference_system=crs,
        georeferenced=georeferenced,
    )


class TestAnalysisRepositoryCrud:
    def test_create_then_get_round_trips(self, repository: PostgresAnalysisRepository) -> None:
        record = _record()

        repository.create(record)
        fetched = repository.get(record.analysis_id)

        assert fetched is not None
        assert fetched.analysis_id == record.analysis_id
        assert fetched.status is AnalysisStatus.UPLOADED
        assert fetched.original_filename == "aerial.png"
        assert fetched.buildings is None
        assert fetched.summary is None
        assert fetched.attempt_count == 0

    def test_get_returns_none_for_unknown_id(
        self, repository: PostgresAnalysisRepository
    ) -> None:
        assert repository.get(uuid4()) is None

    def test_update_status_transitions_and_touches_updated_at(
        self, repository: PostgresAnalysisRepository
    ) -> None:
        record = _record()
        repository.create(record)

        updated = repository.update_status(record.analysis_id, AnalysisStatus.QUEUED)

        assert updated.status is AnalysisStatus.QUEUED
        assert updated.updated_at >= record.updated_at

    def test_update_status_raises_for_unknown_id(
        self, repository: PostgresAnalysisRepository
    ) -> None:
        with pytest.raises(AnalysisNotFoundError):
            repository.update_status(uuid4(), AnalysisStatus.QUEUED)

    def test_save_result_sets_completed_and_stores_buildings(
        self, repository: PostgresAnalysisRepository
    ) -> None:
        record = _record()
        repository.create(record)
        buildings = [_building("b0", DamageClass.DESTROYED), _building("b1", DamageClass.MINOR)]
        summary = DamageSummary(
            total_buildings=2,
            damaged_buildings=2,
            severely_damaged=1,
            destroyed=1
        )
        model_metadata = ModelStatus(
            model_loaded=True, model_name="test", model_version="1", device="cpu"
        )

        result = repository.save_result(
            record.analysis_id, summary=summary, buildings=buildings, model_metadata=model_metadata
        )

        assert result.status is AnalysisStatus.COMPLETED
        assert result.summary == summary
        assert result.model_metadata == model_metadata
        assert result.buildings is not None
        assert len(result.buildings) == 2
        assert {b.building_id for b in result.buildings} == {"b0", "b1"}

    def test_save_result_called_twice_replaces_not_duplicates_buildings(
        self, repository: PostgresAnalysisRepository
    ) -> None:
        """Idempotency: a retried/duplicate job must not accumulate
        duplicate BuildingDamage rows — see
        `docs/architecture/production.md`, "Idempotency / retries"."""
        record = _record()
        repository.create(record)
        summary = DamageSummary(
            total_buildings=1,
            damaged_buildings=1,
            severely_damaged=0,
            destroyed=0
        )
        model_metadata = ModelStatus(
            model_loaded=True, model_name="test", model_version="1", device="cpu"
        )

        repository.save_result(
            record.analysis_id,
            summary=summary,
            buildings=[_building("b0", DamageClass.MINOR)],
            model_metadata=model_metadata,
        )
        second = repository.save_result(
            record.analysis_id,
            summary=summary,
            buildings=[_building("b0", DamageClass.MAJOR)],
            model_metadata=model_metadata,
        )

        assert second.buildings is not None
        assert len(second.buildings) == 1
        assert second.buildings[0].damage_class == DamageClass.MAJOR

    def test_save_failure_sets_failed_with_structured_reason(
        self, repository: PostgresAnalysisRepository
    ) -> None:
        record = _record()
        repository.create(record)

        result = repository.save_failure(
            record.analysis_id,
            AnalysisFailure(code=AnalysisErrorCode.MODEL_UNAVAILABLE, message="no model"),
        )

        assert result.status is AnalysisStatus.FAILED
        assert result.failure is not None
        assert result.failure.code is AnalysisErrorCode.MODEL_UNAVAILABLE
        assert result.failure.message == "no model"
        assert result.buildings is None

    def test_save_failure_raises_for_unknown_id(
        self, repository: PostgresAnalysisRepository
    ) -> None:
        with pytest.raises(AnalysisNotFoundError):
            repository.save_failure(
                uuid4(), AnalysisFailure(code=AnalysisErrorCode.MODEL_UNAVAILABLE, message="x")
            )

    def test_increment_attempt_count_increments_and_persists(
        self, repository: PostgresAnalysisRepository
    ) -> None:
        record = _record()
        repository.create(record)

        first = repository.increment_attempt_count(record.analysis_id)
        second = repository.increment_attempt_count(record.analysis_id)

        assert first == 1
        assert second == 2
        assert repository.get(record.analysis_id).attempt_count == 2  # type: ignore[union-attr]

    def test_increment_attempt_count_raises_for_unknown_id(
        self, repository: PostgresAnalysisRepository
    ) -> None:
        with pytest.raises(AnalysisNotFoundError):
            repository.increment_attempt_count(uuid4())


class TestSpatialRepository:
    def test_get_buildings_is_none_before_analysis_completes(
        self,
        repository: PostgresAnalysisRepository,
        spatial_repository: PostgresSpatialRepository,
    ) -> None:
        record = _record(status=AnalysisStatus.PROCESSING)
        repository.create(record)

        assert spatial_repository.get_buildings(record.analysis_id) is None

    def test_get_buildings_returns_none_for_unknown_analysis(
        self, spatial_repository: PostgresSpatialRepository
    ) -> None:
        assert spatial_repository.get_buildings(uuid4()) is None

    def test_get_buildings_returns_list_once_completed_even_if_empty(
        self,
        repository: PostgresAnalysisRepository,
        spatial_repository: PostgresSpatialRepository,
    ) -> None:
        record = _record()
        repository.create(record)
        summary = DamageSummary(
            total_buildings=0,
            damaged_buildings=0,
            severely_damaged=0,
            destroyed=0
        )
        model_metadata = ModelStatus(
            model_loaded=True, model_name="test", model_version="1", device="cpu"
        )
        repository.save_result(
            record.analysis_id, summary=summary, buildings=[], model_metadata=model_metadata
        )

        result = spatial_repository.get_buildings(record.analysis_id)

        assert result == []  # not None — distinct from "not processed yet"

    def test_reads_the_buildings_written_by_the_analysis_repository(
        self,
        repository: PostgresAnalysisRepository,
        spatial_repository: PostgresSpatialRepository,
    ) -> None:
        """The two repositories share the same underlying table — see
        `app/services/postgres_spatial_repository.py`'s module docstring
        for why `save_buildings()` is a deliberate no-op there."""
        record = _record()
        repository.create(record)
        summary = DamageSummary(
            total_buildings=3,
            damaged_buildings=2,
            severely_damaged=1,
            destroyed=1
        )
        model_metadata = ModelStatus(
            model_loaded=True, model_name="test", model_version="1", device="cpu"
        )
        repository.save_result(
            record.analysis_id,
            summary=summary,
            buildings=[
                _building("b0", DamageClass.NO_DAMAGE),
                _building("b1", DamageClass.MAJOR),
                _building("b2", DamageClass.DESTROYED),
            ],
            model_metadata=model_metadata,
        )

        # save_buildings() is a documented no-op for this implementation.
        spatial_repository.save_buildings(record.analysis_id, [])

        all_buildings = spatial_repository.get_buildings(record.analysis_id)
        damaged = spatial_repository.get_damaged_buildings(record.analysis_id)
        severe = spatial_repository.get_severely_damaged_buildings(record.analysis_id)
        high_priority = spatial_repository.get_high_priority_buildings(record.analysis_id)

        assert all_buildings is not None
        assert len(all_buildings) == 3
        assert {b.building_id for b in damaged} == {"b1", "b2"}
        assert {b.building_id for b in severe} == {"b1", "b2"}
        assert "b2" in {b.building_id for b in high_priority}

    def test_get_buildings_in_bounding_box_filters_by_geometry(
        self,
        repository: PostgresAnalysisRepository,
        spatial_repository: PostgresSpatialRepository,
    ) -> None:
        record = _record()
        repository.create(record)
        summary = DamageSummary(
            total_buildings=2,
            damaged_buildings=1,
            severely_damaged=0,
            destroyed=0
        )
        model_metadata = ModelStatus(
            model_loaded=True, model_name="test", model_version="1", device="cpu"
        )
        inside = _building(
            "inside", DamageClass.MINOR, geometry=PointGeometry(coordinates=(5.0, 5.0))
        )
        outside = _building(
            "outside", DamageClass.MINOR, geometry=PointGeometry(coordinates=(50.0, 50.0))
        )
        repository.save_result(
            record.analysis_id,
            summary=summary,
            buildings=[inside, outside],
            model_metadata=model_metadata,
        )

        bbox = BoundingBoxGeometry(coordinates=(0.0, 0.0, 10.0, 10.0))
        result = spatial_repository.get_buildings_in_bounding_box(record.analysis_id, bbox)

        assert {b.building_id for b in result} == {"inside"}

    def test_crs_is_preserved_through_the_round_trip(
        self,
        repository: PostgresAnalysisRepository,
        spatial_repository: PostgresSpatialRepository,
    ) -> None:
        """CRS safety (Milestone F3/F5 requirement): IMAGE-space geometry
        must never silently become WGS84 (or vice versa) through
        persistence."""
        record = _record()
        repository.create(record)
        summary = DamageSummary(
            total_buildings=2,
            damaged_buildings=0,
            severely_damaged=0,
            destroyed=0
        )
        model_metadata = ModelStatus(
            model_loaded=True, model_name="test", model_version="1", device="cpu"
        )
        image_space = _building(
            "pixels",
            DamageClass.NO_DAMAGE,
            crs=CoordinateReferenceSystem.IMAGE,
            georeferenced=False,
        )
        geographic = _building(
            "geo", DamageClass.NO_DAMAGE, crs=CoordinateReferenceSystem.WGS84, georeferenced=True
        )
        repository.save_result(
            record.analysis_id,
            summary=summary,
            buildings=[image_space, geographic],
            model_metadata=model_metadata,
        )

        result = {b.building_id: b for b in spatial_repository.get_buildings(record.analysis_id)}  # type: ignore[union-attr]

        assert result["pixels"].coordinate_reference_system is CoordinateReferenceSystem.IMAGE
        assert result["pixels"].georeferenced is False
        assert result["geo"].coordinate_reference_system is CoordinateReferenceSystem.WGS84
        assert result["geo"].georeferenced is True

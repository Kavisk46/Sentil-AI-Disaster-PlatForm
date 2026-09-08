"""ORM models for Postgres-backed persistence (Milestone F5).

Deliberately a **small** relational schema, not a one-table-per-Pydantic-
schema mirror:

- `AnalysisORM` persists the analysis lifecycle record — the same fields
  `AnalysisRecord` (`app/services/analysis_repository.py`) already
  carries, plus `attempt_count` (new — see "Idempotency/retries" in
  `docs/architecture/production.md`).
- `BuildingDamageORM` persists one row per detected building — the
  normalized "buildings" table `app/services/spatial_repository.py`'s own
  module docstring already anticipated ("a real `geometry`/`geography`
  column with a spatial index... `save_buildings` becomes an INSERT/UPSERT
  into that `buildings` table").

**Deliberately NOT persisted here**: `SearchZone`, `Recommendation`,
`Route`. F2/F3's own established, tested design principle is that these
are *pure functions* of `AffectedArea`/`Resource`/config, recomputed
fresh on every request specifically so they never go stale relative to
config changes (see `app/services/intelligence_service.py`'s module
docstring: "computed fresh on every call, never cached"). Persisting
them as a separate table would either (a) silently reintroduce the exact
staleness F2/F3 deliberately avoided, or (b) require recomputing them
anyway and only ever reading the recomputed value — in which case the
table would exist but serve no purpose. See
`docs/architecture/production.md`, "Persistence," for the full
reasoning.

Nested, small, non-relationally-queried structures (`DamageSummary`,
`ModelStatus`, a building's `bounding_box`/`geometry`) are stored as JSON
columns — mirroring exactly what `app.ml.schemas`'s own Pydantic models
already validate — rather than exploded into further tables nothing
queries by their internal fields.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class AnalysisORM(Base):
    __tablename__ = "analyses"

    analysis_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_name: Mapped[str] = mapped_column(String(128), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    # `timezone=True` explicitly — without it, SQLite (used by the test
    # suite's isolated databases — see `tests/test_postgres_repositories.py`)
    # silently returns naive `datetime` objects on read, which then fail
    # to compare against the timezone-aware `datetime.now(UTC)` values
    # every domain layer in this codebase already uses throughout.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Populated only once status == COMPLETED — mirrors AnalysisRecord's
    # own "only once completed" contract exactly; never fabricated.
    summary: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    model_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)

    # Populated only once status == FAILED.
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Milestone F5: how many times a worker has picked up this analysis
    # for processing — bumped once per job attempt (see
    # app/worker/tasks.py), independent of which queue backend is in use.
    # Observability + a basis for "do not endlessly retry" reasoning, not
    # itself an enforcement mechanism (JOB_MAX_RETRIES/RQ's own Retry
    # enforces the bound — see app/services/job_queue.py).
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)

    buildings: Mapped[list["BuildingDamageORM"]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        order_by="BuildingDamageORM.id",
    )


class BuildingDamageORM(Base):
    __tablename__ = "building_damages"
    __table_args__ = (Index("ix_building_damages_analysis_id", "analysis_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.analysis_id", ondelete="CASCADE"), nullable=False
    )
    building_id: Mapped[str] = mapped_column(String(64), nullable=False)
    damage_class: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(nullable=False)
    bounding_box: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    geometry: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    coordinate_reference_system: Mapped[str] = mapped_column(String(16), nullable=False)
    georeferenced: Mapped[bool] = mapped_column(nullable=False, default=False)

    analysis: Mapped[AnalysisORM] = relationship(back_populates="buildings")

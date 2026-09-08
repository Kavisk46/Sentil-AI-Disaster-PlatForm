"""PostgreSQL-backed `SpatialRepository` (Milestone F5).

Reads from the exact same `building_damages` table
`PostgresAnalysisRepository.save_result()` writes to — the normalized
"buildings" table `spatial_repository.py`'s own module docstring already
anticipated. `save_buildings()` is deliberately a no-op here: in the
in-memory world, `AnalysisRepository` and `SpatialRepository` are two
separate dicts that `AnalysisProcessingService._save_result()` populates
independently (see that method — it calls both
`self._repository.save_result(...)` and
`self._spatial_repository.save_buildings(...)` with the same buildings).
In Postgres they are two *views* over one physical table, so writing the
row once (via `PostgresAnalysisRepository`, which already runs first in
`_save_result()`) and never a second time avoids either a duplicate
`INSERT` or an ordering dependency between the two calls.
"""

from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AnalysisORM
from app.ml.geospatial.geometry import BoundingBoxGeometry
from app.ml.geospatial.priority import is_high_priority
from app.ml.schemas import BuildingDamage, DamageClass
from app.schemas.analysis import AnalysisStatus
from app.services.postgres_analysis_repository import to_building
from app.services.spatial_repository import envelope_of

_SEVERE_CLASSES = frozenset({DamageClass.MAJOR, DamageClass.DESTROYED})


class PostgresSpatialRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def save_buildings(self, analysis_id: UUID, buildings: object) -> None:
        # No-op — see module docstring. Buildings for `analysis_id` are
        # already persisted by `PostgresAnalysisRepository.save_result()`,
        # which `AnalysisProcessingService._save_result()` always calls
        # first.
        return None

    def get_buildings(self, analysis_id: UUID) -> list[BuildingDamage] | None:
        with self._session_factory() as session:
            analysis = session.get(AnalysisORM, analysis_id)
            if analysis is None:
                return None
            # `None` (not yet saved) is distinct from `[]` (saved, zero
            # buildings) — mirrors `InMemorySpatialRepository`'s own
            # documented contract. An analysis row exists from the moment
            # it's created (upload time), well before any buildings are
            # ever saved (completion time), so the emptiness of the
            # `buildings` relationship alone can't tell these apart —
            # only `status == COMPLETED` can.
            if analysis.status != AnalysisStatus.COMPLETED.value:
                return None
            return [to_building(b) for b in analysis.buildings]

    def get_damaged_buildings(self, analysis_id: UUID) -> list[BuildingDamage]:
        buildings = self.get_buildings(analysis_id) or []
        return [b for b in buildings if b.damage_class != DamageClass.NO_DAMAGE]

    def get_severely_damaged_buildings(self, analysis_id: UUID) -> list[BuildingDamage]:
        buildings = self.get_buildings(analysis_id) or []
        return [b for b in buildings if b.damage_class in _SEVERE_CLASSES]

    def get_buildings_in_bounding_box(
        self, analysis_id: UUID, bbox: BoundingBoxGeometry
    ) -> list[BuildingDamage]:
        result = []
        for building in self.get_buildings(analysis_id) or []:
            envelope = envelope_of(building)
            if envelope is not None and envelope.intersects(bbox):
                result.append(building)
        return result

    def get_high_priority_buildings(self, analysis_id: UUID) -> list[BuildingDamage]:
        return [
            b for b in self.get_buildings(analysis_id) or [] if is_high_priority(b.damage_class)
        ]

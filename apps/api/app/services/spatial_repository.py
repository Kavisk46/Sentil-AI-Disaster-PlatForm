"""Repository abstraction for building-level spatial/geometry data —
prepares the seam a PostGIS-backed implementation will fill later, without
introducing a database now (still in-memory, matching
`app.services.analysis_repository`'s own current tradeoff).

Deliberately separate from `AnalysisRepository`: in a normalized PostGIS
schema, an analysis's building geometries would live in their own
`buildings` table (one row per building, a real `geometry`/`geography`
column with a spatial index) rather than embedded in the `analyses` row —
this interface already reflects that split, so promoting
`InMemorySpatialRepository` to a real PostGIS implementation later changes
no caller (`AnalysisProcessingService`, `DamageMapService`). If/when a real
database is introduced, `save_buildings` becomes an `INSERT`/`UPSERT` into
that `buildings` table (ideally in the same transaction that writes the
analysis's `completed` status) and every `get_*`/`query_*` method becomes a
`SELECT ... WHERE analysis_id = ...` with the documented PostGIS operator.

Every query is scoped to one `analysis_id`: SentinelAI has no
cross-analysis spatial queries yet (e.g. "all damaged buildings across
every uploaded image in a region") — a natural PostGIS extension once
there's a real use case, not implemented speculatively here.
"""

import threading
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.ml.geospatial.geometry import BoundingBoxGeometry, PointGeometry, PolygonGeometry
from app.ml.geospatial.priority import is_high_priority
from app.ml.schemas import BuildingDamage, DamageClass

_SEVERE_CLASSES = frozenset({DamageClass.MAJOR, DamageClass.DESTROYED})


class SpatialRepository(Protocol):
    def save_buildings(self, analysis_id: UUID, buildings: Sequence[BuildingDamage]) -> None:
        """Persist the spatial view of `analysis_id`'s buildings. Called
        once, right after `AnalysisProcessingService` saves a completed
        result — see `app/services/analysis_processing_service.py`."""
        ...

    def get_buildings(self, analysis_id: UUID) -> list[BuildingDamage] | None:
        """All buildings for `analysis_id`, or `None` if nothing has been
        saved for it yet (distinct from an empty list, which means "saved,
        but the analysis had zero buildings")."""
        ...

    def get_damaged_buildings(self, analysis_id: UUID) -> list[BuildingDamage]:
        """Buildings with any damage (`damage_class != NO_DAMAGE`). The
        PostGIS equivalent is `WHERE damage_class != 'no_damage'`."""
        ...

    def get_severely_damaged_buildings(self, analysis_id: UUID) -> list[BuildingDamage]:
        """Buildings classified `MAJOR` or `DESTROYED` — mirrors
        `app.ml.postprocessing`'s `severely_damaged` convention."""
        ...

    def get_buildings_in_bounding_box(
        self, analysis_id: UUID, bbox: BoundingBoxGeometry
    ) -> list[BuildingDamage]:
        """Buildings whose geometry intersects `bbox`. Buildings with no
        geometry are never included. The PostGIS equivalent is
        `WHERE ST_Intersects(geometry, :bbox)`."""
        ...

    def get_high_priority_buildings(self, analysis_id: UUID) -> list[BuildingDamage]:
        """Buildings at `DamagePriority.HIGH` or `.CRITICAL` — see
        `app/ml/geospatial/priority.py`. The PostGIS equivalent is
        `WHERE priority_rank >= :threshold ORDER BY priority_rank DESC`."""
        ...


def envelope_of(building: BuildingDamage) -> BoundingBoxGeometry | None:
    """The axis-aligned bounding envelope of `building.geometry` — every
    `Geometry` variant has one, even a `PolygonGeometry` (a future
    PostGIS-backed implementation would use `ST_Envelope` for this).
    `None` when the building has no geometry at all."""
    geometry = building.geometry
    if geometry is None:
        return None
    if isinstance(geometry, BoundingBoxGeometry):
        return geometry
    if isinstance(geometry, PointGeometry):
        x, y = geometry.coordinates
        return BoundingBoxGeometry(coordinates=(x, y, x, y))
    if isinstance(geometry, PolygonGeometry):
        xs = [x for ring in geometry.coordinates for x, _ in ring]
        ys = [y for ring in geometry.coordinates for _, y in ring]
        return BoundingBoxGeometry(coordinates=(min(xs), min(ys), max(xs), max(ys)))
    raise TypeError(f"Unsupported geometry type: {type(geometry)!r}")  # pragma: no cover


class InMemorySpatialRepository:
    """Process-local, non-persistent — same tradeoffs as
    `InMemoryAnalysisRepository`. A single instance must be shared across
    requests (see `app/api/deps.py`) to remember anything between calls."""

    def __init__(self) -> None:
        self._buildings: dict[UUID, tuple[BuildingDamage, ...]] = {}
        self._lock = threading.Lock()

    def save_buildings(self, analysis_id: UUID, buildings: Sequence[BuildingDamage]) -> None:
        with self._lock:
            self._buildings[analysis_id] = tuple(buildings)

    def get_buildings(self, analysis_id: UUID) -> list[BuildingDamage] | None:
        with self._lock:
            stored = self._buildings.get(analysis_id)
            return list(stored) if stored is not None else None

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

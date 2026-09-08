"""Converts raw model output into the structured `DamageAnalysis` contract.

This is where a list of `RawDetection` (model-space, from
`app/ml/model.py`) becomes `BuildingDamage` entries, an aggregate
`DamageSummary`, and a wrapping `DamageAnalysis` — nothing here invents a
detection; it only reshapes whatever the model actually produced.

Milestone 5: this is also where each `BuildingDamage` gets its "Spatial
Representation" (`geometry`/`coordinate_reference_system`/`georeferenced`)
via `app.ml.geospatial.spatial_builder.image_space_geometry` — always
pixel-space today, since no georeferencing metadata source exists for
ordinary image uploads (see `app.ml.geospatial.georeferencing`).
"""

from collections.abc import Sequence
from uuid import UUID

from app.ml.geospatial.spatial_builder import image_space_geometry
from app.ml.model import RawDetection
from app.ml.schemas import BuildingDamage, DamageAnalysis, DamageClass, DamageSummary
from app.schemas.analysis import AnalysisStatus

_SEVERE_CLASSES = frozenset({DamageClass.MAJOR, DamageClass.DESTROYED})


class PostprocessingError(RuntimeError):
    """Raised when a model's raw detections cannot be assembled into a
    valid `DamageAnalysis` (Milestone F4) — e.g. a malformed detection
    that fails `BuildingDamage`'s own validation. Maps to
    `AnalysisErrorCode.POSTPROCESSING_FAILURE`
    (`app/services/analysis_processing_service.py`), distinct from
    `INFERENCE_FAILURE` (the model itself failing) so the two stages
    remain independently diagnosable."""


def summarize_buildings(buildings: Sequence[BuildingDamage]) -> DamageSummary:
    """Aggregate per-building predictions into `DamageSummary` counts."""
    return DamageSummary(
        total_buildings=len(buildings),
        damaged_buildings=sum(1 for b in buildings if b.damage_class != DamageClass.NO_DAMAGE),
        severely_damaged=sum(1 for b in buildings if b.damage_class in _SEVERE_CLASSES),
        destroyed=sum(1 for b in buildings if b.damage_class == DamageClass.DESTROYED),
    )


def build_analysis(
    analysis_id: UUID,
    status: AnalysisStatus,
    detections: Sequence[RawDetection],
) -> DamageAnalysis:
    """Assemble a `DamageAnalysis` from a model's raw detections.

    `building_id`s are assigned here (`building_0`, `building_1`, ...) —
    a real model's raw output doesn't inherently carry a semantic
    identifier; that's part of what postprocessing establishes.
    """
    buildings = []
    for index, detection in enumerate(detections):
        geometry, crs, georeferenced = image_space_geometry(detection.bounding_box)
        buildings.append(
            BuildingDamage(
                building_id=f"building_{index}",
                damage_class=detection.damage_class,
                confidence=detection.confidence,
                bounding_box=detection.bounding_box,
                geometry=geometry,
                coordinate_reference_system=crs,
                georeferenced=georeferenced,
            )
        )

    return DamageAnalysis(
        analysis_id=analysis_id,
        status=status,
        summary=summarize_buildings(buildings),
        buildings=buildings,
    )

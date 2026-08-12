"""Typed contracts for damage-intelligence results.

These are the *shapes* the eventual model output will take — not model
output itself. No route returns these yet (see `apps/api/README.md`).
`DamageAnalysis.status` reuses `app.schemas.analysis.AnalysisStatus`
deliberately: a damage analysis is the same upload-to-result lifecycle
introduced in Milestone 2, just enriched with results once processing
completes, not a parallel concept with its own states.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.ml.geospatial.geometry import Geometry
from app.ml.spatial import BoundingBox
from app.schemas.analysis import AnalysisFailure, AnalysisStatus


class DamageClass(StrEnum):
    """Normalized damage severity, aligned with the xBD/xView2 joint damage
    scale (`no-damage` / `minor-damage` / `major-damage` / `destroyed`) —
    see `apps/api/README.md` for why that scheme was chosen. These are
    *label* values a model will eventually be trained to predict; nothing
    in this codebase currently produces them from real imagery.
    """

    NO_DAMAGE = "no_damage"
    MINOR = "minor"
    MAJOR = "major"
    DESTROYED = "destroyed"


class BuildingDamage(BaseModel):
    """One building-level damage prediction.

    `bounding_box` is `None` whenever the model that produced this
    prediction only classified a known region rather than locating it
    itself (true for every model this codebase has as of Milestone 3C —
    see `app/ml/localizer.py`). Never populate it with an invented
    location.

    `geometry`/`coordinate_reference_system`/`georeferenced` (Milestone 5)
    are the "Spatial Representation" of this same prediction — see
    `app.ml.geospatial`. `geometry` is derived from `bounding_box` by
    `app.ml.postprocessing.build_analysis` (via
    `app.ml.geospatial.spatial_builder`), so it's `None` under exactly the
    same condition `bounding_box` is `None`: no location, no geometry,
    never a fabricated one. `georeferenced=False`/`coordinate_reference_system
    =IMAGE` is the only case this codebase actually produces today — no
    real georeferencing metadata source exists yet (see
    `app.ml.geospatial.georeferencing`).
    """

    building_id: str
    damage_class: DamageClass
    confidence: float = Field(ge=0.0, le=1.0)
    bounding_box: BoundingBox | None = None
    geometry: Geometry | None = None
    coordinate_reference_system: CoordinateReferenceSystem = CoordinateReferenceSystem.IMAGE
    georeferenced: bool = False


class DamageSummary(BaseModel):
    """Aggregate counts across all buildings in an analysis.

    `severely_damaged` is defined as `MAJOR` + `DESTROYED` — the
    convention this platform uses for prioritization; `destroyed` is
    reported separately since it drives different operational decisions
    than "severely damaged but standing."
    """

    total_buildings: int = Field(ge=0)
    damaged_buildings: int = Field(ge=0)
    severely_damaged: int = Field(ge=0)
    destroyed: int = Field(ge=0)


class ModelStatus(BaseModel):
    """Whether a real model is actually loaded and ready to serve
    predictions — see `app/ml/model.py`. Never implies availability that
    isn't real."""

    model_loaded: bool
    model_name: str
    model_version: str
    device: str


class DamageAnalysis(BaseModel):
    """The result of `GET /api/v1/analysis/{analysis_id}` — this *is* the
    analysis result contract; there is deliberately no second schema for
    it (see `app/services/analysis_processing_service.py`).

    `summary`/`buildings`/`model_metadata` are only populated once `status
    == AnalysisStatus.COMPLETED`; `failure` only once `status ==
    AnalysisStatus.FAILED`. For every other status they are absent (`None`
    / empty), never fabricated.
    """

    analysis_id: UUID
    status: AnalysisStatus
    summary: DamageSummary | None = None
    buildings: list[BuildingDamage] = Field(default_factory=list)
    model_metadata: ModelStatus | None = None
    failure: AnalysisFailure | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

"""Response schema for `GET /api/v1/analysis/{analysis_id}/damage-map`."""

from uuid import UUID

from pydantic import BaseModel

from app.ml.geospatial.geojson import FeatureCollection
from app.schemas.analysis import AnalysisStatus


class DamageMapResponse(BaseModel):
    """`available=False` means `feature_collection` is empty and `reason`
    explains why (the analysis isn't `completed` yet, or it completed with
    no mappable building geometry) — never a fabricated map. See
    apps/api/README.md ("Damage-map API").
    """

    analysis_id: UUID
    status: AnalysisStatus
    available: bool
    reason: str | None = None
    feature_collection: FeatureCollection

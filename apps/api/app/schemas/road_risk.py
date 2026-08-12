"""Response schema for `GET /api/v1/analysis/{analysis_id}/road-risk`."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.roads.schemas import RoadEdge
from app.schemas.analysis import AnalysisStatus


class RoadRiskResponse(BaseModel):
    """`available=False` means `edges` is empty and `reason` explains why
    (the analysis isn't `completed` yet, it has no georeferenced damage
    geometry, or no road network is loaded) — never a fabricated risk
    assessment. See apps/api/README.md ("Road risk model").

    `edges` reuses `app.roads.schemas.RoadEdge` directly (with
    `risk_score`/`risk_level`/`risk_sources` populated) rather than a
    second, parallel edge type — a directed `(source_node, target_node)`
    pair already identifies which physical edge each entry describes.
    """

    analysis_id: UUID
    status: AnalysisStatus
    available: bool
    reason: str | None = None
    edges: list[RoadEdge] = Field(default_factory=list)

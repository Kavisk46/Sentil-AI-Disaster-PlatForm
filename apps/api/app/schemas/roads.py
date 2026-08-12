"""Response schema for `GET /api/v1/roads/status`."""

from pydantic import BaseModel

from app.ml.geospatial.geometry import BoundingBoxGeometry


class RoadNetworkStatusResponse(BaseModel):
    """`loaded=False` means no road network has been ingested for any
    region yet — `node_count`/`edge_count` are `0` and `bounds` is `None`,
    never fabricated placeholder values. `message` explains why whenever
    `loaded` is `False`; see apps/api/README.md ("Road-network status
    API").
    """

    loaded: bool
    node_count: int
    edge_count: int
    bounds: BoundingBoxGeometry | None = None
    message: str | None = None

"""Request schema for `POST /api/v1/routing`."""

from uuid import UUID

from pydantic import BaseModel

from app.roads.schemas import GeographicCoordinate
from app.routing.schemas import RoutingMode


class RoutingRequest(BaseModel):
    """`start`/`destination` are validated WGS84 coordinates
    (`GeographicCoordinate`, reused from `app.roads.schemas` — the same
    validation `RoadNode` itself uses); they are not assumed to exactly
    match a graph node — see `app.routing.nearest_node`. `mode` is
    required (no default): `distance_only` and `risk_aware` produce
    meaningfully different results, so a caller must say which one it
    wants rather than relying on an implicit default.
    """

    analysis_id: UUID
    start: GeographicCoordinate
    destination: GeographicCoordinate
    mode: RoutingMode

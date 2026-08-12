"""Risk-aware rescue routing endpoint (Milestone 6C).

`POST /api/v1/routing` — not nested under `/analysis/{id}/...` like the
damage-map/road-risk endpoints, since a routing request takes two
analysis-independent inputs (start/destination coordinates) plus
`analysis_id` as a body field, not a natural sub-resource of one specific
analysis's URL.

The route only translates HTTP <-> schema and delegates; nearest-node
resolution, the risk-context lookup, and the shortest-path search all live
in `RoutingService`/`app.routing` — no graph algorithm lives here.
"""

from fastapi import APIRouter, status

from app.api.deps import RoutingServiceDep
from app.routing.schemas import RouteResult
from app.schemas.routing import RoutingRequest

router = APIRouter(prefix="/routing", tags=["routing"])


@router.post(
    "",
    response_model=RouteResult,
    status_code=status.HTTP_200_OK,
    summary="Compute a shortest-distance or risk-aware route",
)
def create_route(request: RoutingRequest, routing_service: RoutingServiceDep) -> RouteResult:
    return routing_service.route(request)

"""Road-network diagnostic endpoint (Milestone 6A).

Only a read-only status check — no OSM ingestion trigger, no raw graph
dump, no routing. See `app/roads/__init__.py` for the full architecture.
"""

from fastapi import APIRouter, status

from app.api.deps import RoadNetworkStatusServiceDep
from app.schemas.roads import RoadNetworkStatusResponse

router = APIRouter(prefix="/roads", tags=["roads"])


@router.get(
    "/status",
    response_model=RoadNetworkStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Whether a road network is loaded, and its size/bounds",
)
def get_road_network_status(
    status_service: RoadNetworkStatusServiceDep,
) -> RoadNetworkStatusResponse:
    return status_service.get_status()

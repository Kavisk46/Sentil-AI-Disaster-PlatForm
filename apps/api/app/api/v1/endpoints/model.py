"""Model readiness/status endpoint (Milestone F4).

Only a read-only status check — no load trigger, no inference. Mirrors
`GET /api/v1/roads/status`'s convention (`app/api/v1/endpoints/roads.py`).
"""

from fastapi import APIRouter, status

from app.api.deps import ModelStatusServiceDep
from app.schemas.model import ModelStatusResponse

router = APIRouter(prefix="/model", tags=["model"])


@router.get(
    "/status",
    response_model=ModelStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Whether the damage-classification model is enabled and loaded",
)
def get_model_status(service: ModelStatusServiceDep) -> ModelStatusResponse:
    return service.get_status()

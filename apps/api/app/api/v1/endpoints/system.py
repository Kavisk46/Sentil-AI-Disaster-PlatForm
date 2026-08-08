"""System metadata endpoint.

Exists to prove out API versioning end-to-end during the backend
foundation phase; it deliberately carries no domain/business logic — note
the route itself does nothing but call the injected service.
"""

from fastapi import APIRouter

from app.api.deps import SystemServiceDep
from app.schemas.system import ServiceInfo

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/info", response_model=ServiceInfo, summary="Service metadata")
async def get_service_info(system_service: SystemServiceDep) -> ServiceInfo:
    return system_service.get_service_info()

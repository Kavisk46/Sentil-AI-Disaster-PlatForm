"""Root endpoint.

`GET /` is unversioned, like `/health`: it's a landing summary for whoever
(or whatever) hits the API base URL, not a resource under the versioned
`/api/v1` business API.
"""

from fastapi import APIRouter

from app.api.deps import SystemServiceDep
from app.schemas.system import ProjectInfo

router = APIRouter(tags=["root"])


@router.get("/", response_model=ProjectInfo, summary="Project information")
async def get_project_info(system_service: SystemServiceDep) -> ProjectInfo:
    return system_service.get_project_info()

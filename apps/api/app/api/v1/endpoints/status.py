"""v1 API availability endpoint.

`GET /api/v1` confirms the v1 API surface itself is reachable, independent
of any specific resource under it (e.g. `/api/v1/system/info`).

This registers directly on the router passed in, rather than defining its
own `APIRouter` included via `include_router`: FastAPI's `include_router`
rejects a sub-router whose own resolved path is empty (`""`) when no
prefix is given to that specific call, which a router mounted at exactly
its parent's root inherently has. Registering directly avoids that, and
avoids the alternative of a `"/"` path — which would resolve to
`/api/v1/` and 307-redirect a bare `/api/v1` request instead of returning
200 directly.
"""

from fastapi import APIRouter

from app.api.deps import SystemServiceDep
from app.schemas.system import ApiVersionStatus


def register(router: APIRouter) -> None:
    @router.get("", response_model=ApiVersionStatus, summary="API v1 availability")
    async def get_v1_status(system_service: SystemServiceDep) -> ApiVersionStatus:
        return system_service.get_api_version_status()

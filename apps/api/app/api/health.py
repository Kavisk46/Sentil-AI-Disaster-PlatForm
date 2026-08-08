"""Unversioned liveness endpoint.

`/health` intentionally lives outside `/api/v1`: it is a platform/
infrastructure concern consumed by orchestrators (Docker, Kubernetes, load
balancers) rather than a versioned business API, and its contract should
never change across API versions.
"""

from fastapi import APIRouter

from app.schemas.health import HealthResponse
from app.utils.datetime import utc_now

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
async def health() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=utc_now())

"""Unversioned liveness/readiness endpoints.

`/health` and `/ready` intentionally live outside `/api/v1`: both are
platform/infrastructure concerns consumed by orchestrators (Docker,
Kubernetes, load balancers) rather than a versioned business API, and
their contracts should never change across API versions.

`/health` — is the process alive at all? Never touches PostgreSQL,
Redis, or the model; a dependency outage must never make this endpoint
report "dead" and get the process killed for no reason.

`/ready` (Milestone F5) — can this process actually serve real requests
right now? Gated on real PostgreSQL + Redis connectivity; model
readiness is reported but never gates it — see
`app/services/readiness_service.py`.
"""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.api.deps import ReadinessServiceDep
from app.schemas.health import HealthResponse, ReadyResponse
from app.utils.datetime import utc_now

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
async def health() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=utc_now())


@router.get(
    "/ready",
    response_model=ReadyResponse,
    summary="Readiness check (database + queue connectivity; model status is informational)",
)
def ready(readiness_service: ReadinessServiceDep) -> JSONResponse:
    result = readiness_service.get_readiness()
    http_status = (
        status.HTTP_200_OK if result.status == "ready" else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(status_code=http_status, content=result.model_dump(mode="json"))

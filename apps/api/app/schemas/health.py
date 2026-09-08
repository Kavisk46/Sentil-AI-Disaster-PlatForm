"""Response schemas for the unversioned `/health` and `/ready` endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness signal, consumed by orchestrators (Docker, load
    balancers): "is the process alive at all?" — deliberately never
    checks PostgreSQL/Redis/the model (see `ReadyResponse` for that);
    a database outage must never make an otherwise-healthy process
    look dead and get killed/restarted for no reason."""

    status: str = Field(examples=["ok"])
    timestamp: datetime = Field(description="UTC time the check was performed.")


class ReadinessCheck(BaseModel):
    name: str
    ready: bool
    detail: str | None = None


class ReadyResponse(BaseModel):
    """Readiness signal (Milestone F5): "can this process actually serve
    real requests right now?" `status="ready"` requires every *gating*
    check (`database`, `queue`) to pass. `model` is reported for
    visibility but never gates readiness — a request can be accepted
    with the model still loading (or disabled); it will simply fail
    honestly (`MODEL_UNAVAILABLE`/`MODEL_LOAD_FAILURE`) once processed,
    exactly like any other explicit, structured failure."""

    status: str = Field(examples=["ready", "not_ready"])
    timestamp: datetime
    checks: list[ReadinessCheck]

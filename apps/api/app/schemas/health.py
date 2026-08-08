"""Response schema for the unversioned `/health` liveness endpoint."""

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness/readiness signal, consumed by orchestrators (Docker, load balancers)."""

    status: str = Field(examples=["ok"])
    timestamp: datetime = Field(description="UTC time the check was performed.")

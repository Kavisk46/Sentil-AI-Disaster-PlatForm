"""Response schemas for infrastructure-level, non-domain metadata.

Domain schemas (incidents, imagery, detections, ...) are out of scope for
the Sprint 2.1 backend foundation and belong in their own modules once that
domain modeling work begins.
"""

from pydantic import BaseModel


class ProjectInfo(BaseModel):
    """Returned by the root `GET /` endpoint — a landing summary for API consumers."""

    name: str
    description: str
    version: str
    docs_url: str


class ServiceInfo(BaseModel):
    """Returned by `GET /api/v1/system/info` — basic, non-sensitive service metadata."""

    name: str
    version: str
    environment: str


class ApiVersionStatus(BaseModel):
    """Returned by `GET /api/v1` — confirms this API version is available."""

    version: str
    status: str

"""Request/response schemas for image ingestion (`POST /api/v1/analysis`).

`AnalysisCreateResponse` is a deliberately narrow contract — analysis_id,
status, and the (sanitized) original filename only. Storage location,
content type, and byte size are tracked internally (see
`app/services/analysis_repository.py`) but never serialized to the client.
"""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class AnalysisStatus(StrEnum):
    """Lifecycle of an uploaded analysis.

    This milestone only ever produces `UPLOADED` — the remaining states
    exist so the contract doesn't change shape once a later milestone
    actually performs AI processing.
    """

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisCreateResponse(BaseModel):
    """Returned by `POST /api/v1/analysis`."""

    analysis_id: UUID
    status: AnalysisStatus
    filename: str

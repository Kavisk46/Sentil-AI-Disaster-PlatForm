"""Request/response schemas for the analysis lifecycle
(`POST`/`GET /api/v1/analysis`).

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

        uploaded -> queued -> processing -> completed
                                          -> failed

    `QUEUED` exists because Milestone 4 actually dispatches processing (as
    a FastAPI background task — see `apps/api/README.md`); it wasn't added
    speculatively before there was a queue to represent.
    """

    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisErrorCode(StrEnum):
    """Machine-readable reason an analysis reached `FAILED`.

    Deliberately a closed set, not an arbitrary string — see
    `apps/api/README.md` ("Model unavailable behavior") for what each one
    means and when it's used.
    """

    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    INFERENCE_FAILURE = "INFERENCE_FAILURE"


class AnalysisFailure(BaseModel):
    """A structured, client-safe failure reason.

    Named distinctly from `app.services.exceptions.AnalysisError` (an
    internal exception base class, not a serializable schema) to avoid
    confusing the two. `message` is always a safe, non-sensitive string —
    never a raw Python exception/traceback; see
    `app/services/analysis_processing_service.py`.
    """

    code: AnalysisErrorCode
    message: str


class AnalysisCreateResponse(BaseModel):
    """Returned by `POST /api/v1/analysis`."""

    analysis_id: UUID
    status: AnalysisStatus
    filename: str

"""Connects the upload lifecycle to the ML inference architecture.

    Route -> AnalysisService [upload]
          -> AnalysisProcessingService [this file — lifecycle orchestration]
              -> DamageInferenceEngine ["Inference Service"]
                  -> DamageModel -> postprocessing -> DamageAnalysis

`AnalysisProcessingService` is deliberately a separate class from
`AnalysisService`: `AnalysisService` owns upload validation/storage only
(unchanged since Milestone 2); this owns the queued/processing/
completed/failed lifecycle and is the only thing that touches both the
repository and the ML inference engine. Neither service imports from the
other.

Processing runs synchronously within `process()` — the "background" part
is that FastAPI's `BackgroundTasks` calls it after the HTTP response for
`POST /api/v1/analysis` has already been sent (see
`app/api/v1/endpoints/analysis.py`), not that this class talks to a queue.
No Redis/Celery/Kafka: `BackgroundTasks` is already part of FastAPI, needs
no new infrastructure, and runs `process()` in the same threadpool a sync
route handler would — safe with `InMemoryAnalysisRepository`'s existing
lock. `process(analysis_id)`'s signature doesn't know or care *how* it was
invoked, so swapping the trigger for a real worker later (Celery, an SQS
consumer, ...) means changing the call site in the route, not this class.

Milestone 5: on a successful result, this also saves the buildings' spatial
representation to `SpatialRepository` (`app/services/spatial_repository.py`)
— a separate store from `AnalysisRepository`, mirroring the normalized
`analyses`/`buildings` table split a real PostGIS schema would use. `GET
/api/v1/analysis/{analysis_id}/damage-map` (`DamageMapService`) reads from
it, not from `AnalysisRepository` directly.
"""

from collections.abc import Sequence
from uuid import UUID

from app.core.logging import get_logger
from app.ml.inference import DamageInferenceEngine
from app.ml.model import ModelNotAvailableError
from app.ml.schemas import BuildingDamage, DamageAnalysis
from app.schemas.analysis import AnalysisErrorCode, AnalysisFailure, AnalysisStatus
from app.services.analysis_repository import (
    AnalysisNotFoundError,
    AnalysisRecord,
    AnalysisRepository,
)
from app.services.file_storage import FileStorage
from app.services.spatial_repository import InMemorySpatialRepository, SpatialRepository

logger = get_logger(__name__)

_MODEL_UNAVAILABLE_MESSAGE_PREFIX = "Analysis could not be completed: "
_GENERIC_INFERENCE_FAILURE_MESSAGE = (
    "Analysis failed during processing. This has been logged for investigation."
)


class AnalysisProcessingService:
    def __init__(
        self,
        repository: AnalysisRepository,
        file_storage: FileStorage,
        inference_engine: DamageInferenceEngine,
        spatial_repository: SpatialRepository | None = None,
    ) -> None:
        self._repository = repository
        self._file_storage = file_storage
        self._inference_engine = inference_engine
        # Milestone 5: defaults to a private instance so existing callers
        # (tests, mainly) that don't care about spatial data don't need to
        # construct one — production DI (`app/api/deps.py`) always passes
        # an explicit, shared singleton instead, so `DamageMapService`
        # reads what this service actually wrote.
        self._spatial_repository: SpatialRepository = (
            spatial_repository or InMemorySpatialRepository()
        )

    def enqueue(self, analysis_id: UUID) -> AnalysisRecord:
        """Transition `uploaded` -> `queued`. Fast and synchronous — called
        from the request path, before `process()` is scheduled to run."""
        return self._repository.update_status(analysis_id, AnalysisStatus.QUEUED)

    def process(self, analysis_id: UUID) -> None:
        """Run `queued` -> `processing` -> `completed`/`failed`.

        Never raises: any failure (including the analysis having vanished,
        which shouldn't happen in practice) is caught and, where possible,
        recorded as a `failed` status rather than propagated — this runs
        detached from any HTTP response, so there is no client to return
        an error to.
        """
        record = self._repository.get(analysis_id)
        if record is None:
            logger.error("process() called for unknown analysis_id=%s", analysis_id)
            return

        if record.status in (AnalysisStatus.COMPLETED, AnalysisStatus.FAILED):
            # Already a terminal state — nothing to (re)do. Guards against
            # e.g. a duplicate background-task dispatch.
            return

        self._repository.update_status(analysis_id, AnalysisStatus.PROCESSING)

        try:
            image_content = self._file_storage.load(storage_name=record.storage_name)
            result = self._inference_engine.analyze(analysis_id, image_content)
        except ModelNotAvailableError as exc:
            logger.info("Analysis %s failed: model unavailable (%s)", analysis_id, exc)
            self._save_failure(
                analysis_id,
                AnalysisErrorCode.MODEL_UNAVAILABLE,
                _MODEL_UNAVAILABLE_MESSAGE_PREFIX + str(exc),
            )
            return
        except Exception:
            # Intentionally broad: any other exception during inference
            # must become a structured, client-safe failure rather than
            # propagate — there is nothing else to catch it here, and the
            # client must never see a raw traceback. The real exception is
            # still logged server-side for debugging.
            logger.exception("Analysis %s failed during inference", analysis_id)
            self._save_failure(
                analysis_id,
                AnalysisErrorCode.INFERENCE_FAILURE,
                _GENERIC_INFERENCE_FAILURE_MESSAGE,
            )
            return

        self._save_result(analysis_id, result)

    def get_analysis(self, analysis_id: UUID) -> DamageAnalysis:
        """Assemble the current `DamageAnalysis` view of `analysis_id`.

        Raises `AnalysisNotFoundError` (mapped to `404` — see
        `app/api/exception_handlers.py`) if unknown.
        """
        record = self._repository.get(analysis_id)
        if record is None:
            raise AnalysisNotFoundError(analysis_id)
        return _to_damage_analysis(record)

    def _save_result(self, analysis_id: UUID, result: DamageAnalysis) -> None:
        if result.summary is None or result.model_metadata is None:
            # Indicates a bug in DamageInferenceEngine.analyze(), not a
            # normal failure mode — it must always populate both on a
            # successful (non-raising) return.
            raise RuntimeError(
                "DamageInferenceEngine.analyze() returned a result missing "
                "summary/model_metadata."
            )
        self._repository.save_result(
            analysis_id,
            summary=result.summary,
            buildings=result.buildings,
            model_metadata=result.model_metadata,
        )
        self._spatial_repository.save_buildings(analysis_id, result.buildings)

    def _save_failure(self, analysis_id: UUID, code: AnalysisErrorCode, message: str) -> None:
        self._repository.save_failure(analysis_id, AnalysisFailure(code=code, message=message))


def _to_damage_analysis(record: AnalysisRecord) -> DamageAnalysis:
    buildings: Sequence[BuildingDamage] = record.buildings or []
    return DamageAnalysis(
        analysis_id=record.analysis_id,
        status=record.status,
        summary=record.summary,
        buildings=list(buildings),
        model_metadata=record.model_metadata,
        failure=record.failure,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )

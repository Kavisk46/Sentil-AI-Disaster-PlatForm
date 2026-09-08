"""The RQ job function actually run by the worker process.

Resolved by import string (`app.services.job_queue._PROCESS_ANALYSIS_JOB_PATH`)
— the API process enqueues a string + args onto Redis and never imports
this module itself, so enqueuing a job never pulls `torch`/`open_clip`
into the API process's memory.

`_get_processing_service()` builds exactly one, real,
eagerly-loaded `AnalysisProcessingService` per worker process — the same
"construct once, cache, reuse" discipline `app/api/deps.py`'s model
caches already apply, just at worker-process scope instead of per
dependency-injection call.
"""

import threading
import time
from uuid import UUID

from app.api.deps import (
    get_analysis_repository,
    get_building_localizer,
    get_damage_classifier,
    get_damage_model,
    get_file_storage,
    get_spatial_repository,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.ml.inference import DamageInferenceEngine
from app.services.analysis_processing_service import AnalysisProcessingService

logger = get_logger(__name__)

_processing_service: AnalysisProcessingService | None = None
_lock = threading.Lock()


def _get_processing_service() -> AnalysisProcessingService:
    global _processing_service
    if _processing_service is not None:
        return _processing_service
    with _lock:
        if _processing_service is None:
            settings = get_settings()
            localizer = get_building_localizer(settings)
            classifier = get_damage_classifier(settings)
            model = get_damage_model(localizer, classifier)
            inference_engine = DamageInferenceEngine(
                model=model, max_image_dimension=settings.MODEL_MAX_IMAGE_DIM
            )
            _processing_service = AnalysisProcessingService(
                repository=get_analysis_repository(settings),
                file_storage=get_file_storage(settings),
                inference_engine=inference_engine,
                spatial_repository=get_spatial_repository(settings),
            )
    return _processing_service


def process_analysis_job(analysis_id: str) -> None:
    """Job entrypoint — `analysis_id` is a plain string (RQ/Redis
    serialize job arguments as strings; a `UUID` isn't natively
    JSON-serializable), parsed back to `UUID` here.

    Never raises for a deterministic, already-recorded outcome
    (`AnalysisProcessingService.process()` itself never raises for those
    — see its own docstring); a genuine infrastructure exception (a
    dropped database/Redis connection) propagates here unchanged, which
    is exactly what lets RQ's own bounded `Retry` (see
    `app.services.job_queue.RedisJobQueue`) retry it — see
    `docs/architecture/production.md`, "Retries."
    """
    analysis_uuid = UUID(analysis_id)
    settings = get_settings()
    repository = get_analysis_repository(settings)
    attempt = repository.increment_attempt_count(analysis_uuid)
    logger.info(
        "analysis_id=%s stage=worker_pickup attempt=%s job=analysis:%s",
        analysis_id,
        attempt,
        analysis_id,
    )

    started = time.perf_counter()
    processing_service = _get_processing_service()
    processing_service.process(analysis_uuid)
    duration_ms = (time.perf_counter() - started) * 1000

    record = repository.get(analysis_uuid)
    status_value = record.status.value if record is not None else "unknown"
    logger.info(
        "analysis_id=%s stage=worker_done status=%s duration_ms=%.1f attempt=%s",
        analysis_id,
        status_value,
        duration_ms,
        attempt,
    )

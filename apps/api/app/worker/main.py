"""Worker process entrypoint (Milestone F5).

    python -m app.worker.main

Eagerly loads the real damage-detection model exactly once, at process
startup — fixing F4's documented in-request cold start (40-150s) by
moving it out of the API process entirely — publishes the resulting
lifecycle state to Redis (`GET /api/v1/model/status` reads it back, see
`app/services/model_status_service.py`), then runs an RQ worker loop
pulling jobs off the `analysis` queue.

Schema management (`alembic upgrade head`) is a separate, explicit step
— this entrypoint deliberately does not create or migrate tables itself;
see `docs/architecture/production.md`, "Local development," and
`docker-compose.yml`.
"""

from redis import Redis
from rq import Queue, Worker

from app.api.deps import get_building_localizer, get_damage_classifier, get_damage_model
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.services.worker_status import ModelLifecycleState, ModelStatusPublisher, WorkerModelStatus
from app.utils.datetime import utc_now

logger = get_logger(__name__)

_QUEUE_NAME = "analysis"


def _publish(
    publisher: ModelStatusPublisher,
    settings: Settings,
    state: ModelLifecycleState,
    *,
    model_loaded: bool = False,
    error: str | None = None,
) -> None:
    publisher.publish(
        WorkerModelStatus(
            lifecycle_state=state,
            enabled=settings.MODEL_ENABLED,
            provider=settings.MODEL_PROVIDER,
            model_name=settings.MODEL_NAME,
            model_version=settings.MODEL_VERSION,
            model_loaded=model_loaded,
            device=settings.MODEL_DEVICE,
            error=error,
            updated_at=utc_now(),
        )
    )


def load_model_eagerly(settings: Settings, publisher: ModelStatusPublisher) -> None:
    """Load the model once, synchronously, before the worker starts
    accepting jobs — a queued job that arrives while this is still
    running simply waits in Redis; it is never picked up half-loaded."""
    if not settings.MODEL_ENABLED:
        _publish(publisher, settings, ModelLifecycleState.UNAVAILABLE)
        logger.info(
            "Model disabled (MODEL_ENABLED=false) — every analysis will end MODEL_UNAVAILABLE."
        )
        return

    _publish(publisher, settings, ModelLifecycleState.MODEL_LOADING)
    logger.info(
        "Loading damage-detection model (provider=%s, name=%s, version=%s, device=%s)...",
        settings.MODEL_PROVIDER,
        settings.MODEL_NAME,
        settings.MODEL_VERSION,
        settings.MODEL_DEVICE,
    )
    try:
        localizer = get_building_localizer(settings)
        classifier = get_damage_classifier(settings)
        model = get_damage_model(localizer, classifier)
        health = model.health()
    except Exception as exc:  # noqa: BLE001 - defensive: never crash worker startup
        logger.exception("Model failed to load.")
        _publish(publisher, settings, ModelLifecycleState.FAILED, error=str(exc)[:500])
        return

    if health.model_loaded:
        _publish(publisher, settings, ModelLifecycleState.READY, model_loaded=True)
        logger.info("Model ready (%s / %s).", health.model_name, health.model_version)
    else:
        _publish(
            publisher,
            settings,
            ModelLifecycleState.FAILED,
            error="Model construction completed but health() reports not loaded.",
        )
        logger.error("Model construction completed but health() reports not loaded.")


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    logger.info(
        "SentinelAI worker starting (concurrency=%s, queue=%s)",
        settings.WORKER_CONCURRENCY,
        _QUEUE_NAME,
    )

    publisher = ModelStatusPublisher(settings.REDIS_URL)
    load_model_eagerly(settings, publisher)

    connection = Redis.from_url(settings.REDIS_URL)
    queue = Queue(_QUEUE_NAME, connection=connection)
    worker = Worker([queue], connection=connection)
    logger.info("Worker ready — listening on queue %r.", _QUEUE_NAME)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()

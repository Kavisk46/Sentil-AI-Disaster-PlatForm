"""Assembles `GET /api/v1/model/status`'s response.

Milestone F5: reads the worker's last-published status over Redis
(`app.services.worker_status.ModelStatusReader`) — **never** constructs
or loads a `DamageModel` itself. This is the architectural fix for F4's
documented cold-start problem: the API process must stay responsive even
while the worker is 40-150 seconds into loading a real CLIP checkpoint.
"""

from app.core.config import Settings
from app.ml.schemas import ModelStatus
from app.schemas.model import ModelStatusResponse
from app.services.worker_status import ModelLifecycleState, ModelStatusReader


class ModelStatusService:
    def __init__(self, settings: Settings, reader: ModelStatusReader) -> None:
        self._settings = settings
        self._reader = reader

    def get_status(self) -> ModelStatusResponse:
        worker_status = self._reader.read()
        if worker_status is None:
            # Nothing published yet — the worker hasn't started, hasn't
            # reached this point yet, or Redis itself is unreachable.
            # Honest "not yet known", never a fabricated "ready".
            return ModelStatusResponse(
                enabled=self._settings.MODEL_ENABLED,
                provider=self._settings.MODEL_PROVIDER,
                lifecycle_state=ModelLifecycleState.STARTING,
                status=ModelStatus(
                    model_loaded=False,
                    model_name=self._settings.MODEL_NAME,
                    model_version=self._settings.MODEL_VERSION,
                    device=self._settings.MODEL_DEVICE,
                ),
                error=None,
            )

        return ModelStatusResponse(
            enabled=worker_status.enabled,
            provider=worker_status.provider,
            lifecycle_state=worker_status.lifecycle_state,
            status=ModelStatus(
                model_loaded=worker_status.model_loaded,
                model_name=worker_status.model_name,
                model_version=worker_status.model_version,
                device=worker_status.device,
            ),
            error=worker_status.error,
        )

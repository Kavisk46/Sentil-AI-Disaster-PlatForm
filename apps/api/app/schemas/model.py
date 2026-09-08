"""Response contract for `GET /api/v1/model/status` (Milestone F4;
extended in F5).

Distinct from `app.ml.schemas.ModelStatus` (which only reports what a
loaded/unloaded model itself knows about) — this wraps it with the
*configuration* context needed to tell "the model was never enabled"
apart from "the model was enabled but failed to load," per this
milestone's readiness requirement.

Milestone F5: the API process no longer constructs or loads a
`DamageModel` itself (see `app.services.worker_status`) — this response
now reflects what the *worker* last published, read back over Redis.
`lifecycle_state`/`error` are new, additive fields; `enabled`/`provider`/
`status` keep their exact F4 meaning.
"""

from pydantic import BaseModel

from app.ml.schemas import ModelStatus
from app.services.worker_status import ModelLifecycleState


class ModelStatusResponse(BaseModel):
    """`enabled=False` means real inference was never attempted
    (`Settings.MODEL_ENABLED=False`) — every analysis will end
    `MODEL_UNAVAILABLE`, by explicit configuration, not a fault.
    `enabled=True` with `status.model_loaded=False` means a real load was
    attempted and did not (yet) succeed — see `status.model_name`/
    `.model_version` for which checkpoint, `lifecycle_state` for exactly
    which phase, and `error` for a short, client-safe reason (never a
    traceback or filesystem path).
    """

    enabled: bool
    provider: str
    status: ModelStatus
    lifecycle_state: ModelLifecycleState
    error: str | None = None

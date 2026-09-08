/** Mirrors `apps/api/app/schemas/model.py` — `GET /api/v1/model/status`
 * (Milestone F4; extended in F5). Reuses `ModelStatus` (`./analysis.ts`)
 * rather than duplicating it.
 *
 * Milestone F5: the API process no longer loads the model itself — this
 * reflects what the separate worker process last published over Redis
 * (`apps/api/app/services/worker_status.py`). `lifecycle_state`/`error`
 * are new, additive fields; `enabled`/`provider`/`status` keep their
 * exact F4 meaning. */

import type { ModelStatus } from "./analysis";

export type ModelLifecycleState =
  | "STARTING"
  | "MODEL_LOADING"
  | "READY"
  | "UNAVAILABLE"
  | "FAILED";

export interface ModelStatusResponse {
  enabled: boolean;
  provider: string;
  status: ModelStatus;
  lifecycle_state: ModelLifecycleState;
  error: string | null;
}

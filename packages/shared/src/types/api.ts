/**
 * Types describing the infrastructure-level shapes exposed by the backend's
 * `/health` and `/api/v1/system/info` endpoints (see
 * `apps/api/app/schemas/common.py`). Domain types (incidents, imagery,
 * detections, ...) are intentionally not defined yet — they belong to a
 * future phase once that domain modeling work begins.
 */

export interface HealthStatus {
  status: string;
}

export interface ServiceInfo {
  name: string;
  version: string;
  environment: string;
}

/** Discriminated union for a fetch result, so callers must handle both branches. */
export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: string };

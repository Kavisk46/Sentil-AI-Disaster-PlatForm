import type { ApiResult, ModelStatusResponse } from "@sentinelai/shared";

import { apiGet } from "@/lib/api-client";

/** Typed client for `GET /api/v1/model/status` (Milestone F4). */
export function getModelStatus(): Promise<ApiResult<ModelStatusResponse>> {
  return apiGet<ModelStatusResponse>("/api/v1/model/status");
}

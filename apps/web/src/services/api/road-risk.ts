import type { ApiResult, RoadNetworkStatusResponse, RoadRiskResponse } from "@sentinelai/shared";

import { apiGet } from "@/lib/api-client";

/** Typed client for road-network/road-risk endpoints
 * (`GET /api/v1/roads/status`, `GET /api/v1/analysis/{id}/road-risk`). */

export function getRoadRisk(analysisId: string): Promise<ApiResult<RoadRiskResponse>> {
  return apiGet<RoadRiskResponse>(`/api/v1/analysis/${analysisId}/road-risk`);
}

export function getRoadNetworkStatus(): Promise<ApiResult<RoadNetworkStatusResponse>> {
  return apiGet<RoadNetworkStatusResponse>("/api/v1/roads/status");
}

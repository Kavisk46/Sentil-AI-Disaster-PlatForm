import type { ApiResult, IncidentBriefing, RouteQuery } from "@sentinelai/shared";

import { apiGet, apiPost } from "@/lib/api-client";

/** Typed client for `GET`/`POST /api/v1/analysis/{id}/summary`
 * (AI incident briefing, Milestone 7). */

export function getIncidentSummary(analysisId: string): Promise<ApiResult<IncidentBriefing>> {
  return apiGet<IncidentBriefing>(`/api/v1/analysis/${analysisId}/summary`);
}

export function regenerateIncidentSummary(
  analysisId: string,
  route?: RouteQuery,
): Promise<ApiResult<IncidentBriefing>> {
  return apiPost<IncidentBriefing>(
    `/api/v1/analysis/${analysisId}/summary`,
    route ? { route } : undefined,
  );
}

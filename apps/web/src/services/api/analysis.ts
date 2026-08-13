import type { AnalysisCreateResponse, ApiResult, DamageAnalysis, DamageMapResponse } from "@sentinelai/shared";

import { apiGet, apiUpload } from "@/lib/api-client";

/**
 * Typed client for the analysis lifecycle
 * (`POST`/`GET /api/v1/analysis`, `GET .../damage-map`). Kept UI-free —
 * consumed only by `hooks/use-analysis.ts`, never called directly from a
 * component (see `docs/architecture/frontend.md`, "API integration").
 */

export function uploadAnalysis(file: File): Promise<ApiResult<AnalysisCreateResponse>> {
  const formData = new FormData();
  formData.append("image", file);
  return apiUpload<AnalysisCreateResponse>("/api/v1/analysis", formData);
}

export function getAnalysis(analysisId: string): Promise<ApiResult<DamageAnalysis>> {
  return apiGet<DamageAnalysis>(`/api/v1/analysis/${analysisId}`);
}

export function getDamageMap(analysisId: string): Promise<ApiResult<DamageMapResponse>> {
  return apiGet<DamageMapResponse>(`/api/v1/analysis/${analysisId}/damage-map`);
}

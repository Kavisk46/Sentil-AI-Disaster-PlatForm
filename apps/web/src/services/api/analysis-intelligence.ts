import type {
  AnalysisIntelligenceContextResponse,
  AnalysisRecommendationsResponse,
  AnalysisSearchZonesResponse,
  ApiResult,
} from "@sentinelai/shared";

import { apiGet } from "@/lib/api-client";

/**
 * Typed client for the F3 analysis-aware intelligence endpoints —
 * `GET /api/v1/analysis/{analysis_id}/intelligence[/search-zones|/recommendations]`.
 * Kept UI-free — consumed only by `hooks/use-analysis-intelligence.ts`.
 * Distinct from `services/api/intelligence.ts` (F2, disaster-scoped, still
 * used for the DEMO-mode path — see `docs/architecture/frontend.md`).
 */

export function getAnalysisIntelligenceContext(
  analysisId: string,
): Promise<ApiResult<AnalysisIntelligenceContextResponse>> {
  return apiGet<AnalysisIntelligenceContextResponse>(
    `/api/v1/analysis/${analysisId}/intelligence`,
  );
}

export function getAnalysisSearchZones(
  analysisId: string,
): Promise<ApiResult<AnalysisSearchZonesResponse>> {
  return apiGet<AnalysisSearchZonesResponse>(
    `/api/v1/analysis/${analysisId}/intelligence/search-zones`,
  );
}

export function getAnalysisRecommendations(
  analysisId: string,
): Promise<ApiResult<AnalysisRecommendationsResponse>> {
  return apiGet<AnalysisRecommendationsResponse>(
    `/api/v1/analysis/${analysisId}/intelligence/recommendations`,
  );
}

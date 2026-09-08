import { useQuery } from "@tanstack/react-query";

import {
  getAnalysisIntelligenceContext,
  getAnalysisRecommendations,
  getAnalysisSearchZones,
} from "@/services/api/analysis-intelligence";

/** `GET /api/v1/analysis/{id}/intelligence`. `enabled` lets the caller
 * gate this on the analysis actually being `completed` — same convention
 * as `hooks/use-road-risk.ts`. */
export function useAnalysisIntelligenceContext(analysisId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: analysisId
      ? (["analysis-intelligence", analysisId] as const)
      : (["analysis-intelligence", "none"] as const),
    queryFn: async () => {
      const result = await getAnalysisIntelligenceContext(analysisId!);
      if (!result.ok) throw new Error(result.error);
      return result.data;
    },
    enabled: analysisId !== null && enabled,
  });
}

/** `GET /api/v1/analysis/{id}/intelligence/search-zones`. */
export function useAnalysisSearchZones(analysisId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: analysisId
      ? (["analysis-intelligence-search-zones", analysisId] as const)
      : (["analysis-intelligence-search-zones", "none"] as const),
    queryFn: async () => {
      const result = await getAnalysisSearchZones(analysisId!);
      if (!result.ok) throw new Error(result.error);
      return result.data;
    },
    enabled: analysisId !== null && enabled,
  });
}

/** `GET /api/v1/analysis/{id}/intelligence/recommendations`. */
export function useAnalysisRecommendations(analysisId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: analysisId
      ? (["analysis-intelligence-recommendations", analysisId] as const)
      : (["analysis-intelligence-recommendations", "none"] as const),
    queryFn: async () => {
      const result = await getAnalysisRecommendations(analysisId!);
      if (!result.ok) throw new Error(result.error);
      return result.data;
    },
    enabled: analysisId !== null && enabled,
  });
}

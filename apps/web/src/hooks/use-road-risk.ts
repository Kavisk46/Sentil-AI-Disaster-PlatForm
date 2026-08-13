import { useQuery } from "@tanstack/react-query";

import { getRoadRisk } from "@/services/api/road-risk";

/** `GET /api/v1/analysis/{id}/road-risk`. `enabled` lets the caller gate
 * this on the analysis actually being `completed` (see
 * `hooks/use-analysis.ts`). */
export function useRoadRisk(analysisId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: analysisId ? (["road-risk", analysisId] as const) : (["road-risk", "none"] as const),
    queryFn: async () => {
      const result = await getRoadRisk(analysisId!);
      if (!result.ok) throw new Error(result.error);
      return result.data;
    },
    enabled: analysisId !== null && enabled,
  });
}

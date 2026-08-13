import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { RouteQuery } from "@sentinelai/shared";

import { getIncidentSummary, regenerateIncidentSummary } from "@/services/api/summary";

const SUMMARY_KEY = (id: string) => ["incident-summary", id] as const;

/** `GET /api/v1/analysis/{id}/summary`. `enabled` lets the caller gate
 * this on the analysis actually being `completed`. */
export function useIncidentSummary(analysisId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: analysisId ? SUMMARY_KEY(analysisId) : (["incident-summary", "none"] as const),
    queryFn: async () => {
      const result = await getIncidentSummary(analysisId!);
      if (!result.ok) throw new Error(result.error);
      return result.data;
    },
    enabled: analysisId !== null && enabled,
  });
}

/** `POST /api/v1/analysis/{id}/summary` — regenerates the briefing,
 * optionally enriched with route context, and refreshes the `GET` query's
 * cache with the new result. */
export function useRegenerateIncidentSummary(analysisId: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (route?: RouteQuery) => {
      if (!analysisId) throw new Error("No active analysis to regenerate a summary for.");
      return regenerateIncidentSummary(analysisId, route);
    },
    onSuccess: (result) => {
      if (result.ok && analysisId) {
        queryClient.setQueryData(SUMMARY_KEY(analysisId), result.data);
      }
    },
  });
}

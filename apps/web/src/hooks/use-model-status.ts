import { useQuery } from "@tanstack/react-query";

import { getModelStatus } from "@/services/api/model";

/** Polls `GET /api/v1/model/status` (Milestone F4) — lets the UI show
 * real model readiness (enabled/loaded/name/version) distinctly from
 * general API connectivity (`hooks/use-api-health.ts`). */
export function useModelStatus() {
  return useQuery({
    queryKey: ["model-status"],
    queryFn: async () => {
      const result = await getModelStatus();
      if (!result.ok) throw new Error(result.error);
      return result.data;
    },
    refetchInterval: 30_000,
  });
}

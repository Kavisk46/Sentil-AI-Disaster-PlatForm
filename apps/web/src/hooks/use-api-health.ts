import { useQuery } from "@tanstack/react-query";
import type { HealthStatus } from "@sentinelai/shared";

import { apiGet } from "@/lib/api-client";

/**
 * Polls the backend's `/health` endpoint. Exists in the foundation phase to
 * prove the frontend, TanStack Query, and the FastAPI backend are wired
 * together end-to-end; later phases will add real data-fetching hooks
 * alongside this one.
 */
export function useApiHealth() {
  return useQuery({
    queryKey: ["api-health"],
    queryFn: async () => {
      const result = await apiGet<HealthStatus>("/health");
      if (!result.ok) {
        throw new Error(result.error);
      }
      return result.data;
    },
    refetchInterval: 30_000,
  });
}

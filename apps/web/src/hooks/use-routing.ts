import { useQuery } from "@tanstack/react-query";
import type { GeographicCoordinate } from "@sentinelai/shared";

import { compareRoutes } from "@/services/api/routing";

/**
 * Fetches both routing modes and derives a `RouteComparison` (see
 * `services/api/routing.ts::compareRoutes`). Enabled only once both a
 * start and destination point have been selected (see
 * `store/incident-store.ts`).
 */
export function useRouteComparison(
  analysisId: string | null,
  start: GeographicCoordinate | null,
  destination: GeographicCoordinate | null,
) {
  const enabled = analysisId !== null && start !== null && destination !== null;

  return useQuery({
    queryKey: enabled
      ? (["route-comparison", analysisId, start, destination] as const)
      : (["route-comparison", "none"] as const),
    queryFn: async () => {
      const result = await compareRoutes(analysisId!, start!, destination!);
      if (!result.ok) throw new Error(result.error);
      return result.data;
    },
    enabled,
  });
}

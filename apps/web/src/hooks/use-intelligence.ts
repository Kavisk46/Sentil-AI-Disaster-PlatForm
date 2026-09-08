import { useQuery } from "@tanstack/react-query";

import {
  getDisasterSummary,
  getIntelligenceResources,
  getRecommendations,
  getSearchZones,
} from "@/services/api/intelligence";

/** `GET /api/v1/intelligence/{disaster_id}` — the disaster record and
 * entity counts. `null` disables the query entirely (no disaster
 * selected yet), the same convention every other `use-*` hook in this
 * codebase follows (see `hooks/use-analysis.ts`). */
export function useDisasterSummary(disasterId: string | null) {
  return useQuery({
    queryKey: disasterId ? ["intelligence-disaster", disasterId] : ["intelligence-disaster", "none"],
    queryFn: async () => {
      const result = await getDisasterSummary(disasterId!);
      if (!result.ok) throw new Error(result.error);
      return result.data;
    },
    enabled: disasterId !== null,
  });
}

/** `GET /api/v1/intelligence/{disaster_id}/search-zones` — ranked search
 * zones, scored server-side from recorded affected areas. */
export function useSearchZones(disasterId: string | null) {
  return useQuery({
    queryKey: disasterId ? ["intelligence-search-zones", disasterId] : ["intelligence-search-zones", "none"],
    queryFn: async () => {
      const result = await getSearchZones(disasterId!);
      if (!result.ok) throw new Error(result.error);
      return result.data;
    },
    enabled: disasterId !== null,
  });
}

/** `GET /api/v1/intelligence/{disaster_id}/resources` — the recorded
 * resource registry for this disaster. */
export function useIntelligenceResources(disasterId: string | null) {
  return useQuery({
    queryKey: disasterId ? ["intelligence-resources", disasterId] : ["intelligence-resources", "none"],
    queryFn: async () => {
      const result = await getIntelligenceResources(disasterId!);
      if (!result.ok) throw new Error(result.error);
      return result.data;
    },
    enabled: disasterId !== null,
  });
}

/** `GET /api/v1/intelligence/{disaster_id}/recommendations` — ranked,
 * rule-based response recommendations. */
export function useRecommendations(disasterId: string | null) {
  return useQuery({
    queryKey: disasterId ? ["intelligence-recommendations", disasterId] : ["intelligence-recommendations", "none"],
    queryFn: async () => {
      const result = await getRecommendations(disasterId!);
      if (!result.ok) throw new Error(result.error);
      return result.data;
    },
    enabled: disasterId !== null,
  });
}

import { useMutation, useQuery } from "@tanstack/react-query";
import type { AnalysisCreateResponse, DamageAnalysis, DamageMapResponse } from "@sentinelai/shared";

import { getAnalysis, getDamageMap, uploadAnalysis } from "@/services/api/analysis";

const ANALYSIS_KEY = (id: string) => ["analysis", id] as const;
const DAMAGE_MAP_KEY = (id: string) => ["damage-map", id] as const;

/** `POST /api/v1/analysis` — kicks off the upload -> queued -> processing
 * -> completed/failed lifecycle. On success, the caller is responsible for
 * setting the returned `analysis_id` as the active analysis (see
 * `store/incident-store.ts`) so `useAnalysis` starts polling it. Accepts
 * an optional `onProgress` (real byte counts, see
 * `lib/api-client.ts::apiUpload`) alongside the file, since
 * TanStack Query's `mutate()` passes a single variables object. */
export function useUploadAnalysis() {
  return useMutation({
    mutationFn: ({
      file,
      onProgress,
    }: {
      file: File;
      onProgress?: (loaded: number, total: number) => void;
    }) => uploadAnalysis(file, onProgress),
  });
}

const TERMINAL_STATUSES = new Set<DamageAnalysis["status"]>(["completed", "failed"]);

/** `GET /api/v1/analysis/{id}` — polls every 2s while the analysis is
 * still `queued`/`processing`/`uploaded`, and stops automatically once it
 * reaches a terminal state (`completed`/`failed`). `null` disables the
 * query entirely (no analysis selected yet). */
export function useAnalysis(analysisId: string | null) {
  return useQuery({
    queryKey: analysisId ? ANALYSIS_KEY(analysisId) : ["analysis", "none"],
    queryFn: async () => {
      const result = await getAnalysis(analysisId!);
      if (!result.ok) throw new Error(result.error);
      return result.data;
    },
    enabled: analysisId !== null,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data || !TERMINAL_STATUSES.has(data.status)) return 2000;
      return false;
    },
  });
}

/** `GET /api/v1/analysis/{id}/damage-map` — only meaningful once the
 * analysis has reached a terminal state, so callers pass `enabled`
 * explicitly rather than this hook guessing from status. */
export function useDamageMap(analysisId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: analysisId ? DAMAGE_MAP_KEY(analysisId) : ["damage-map", "none"],
    queryFn: async () => {
      const result = await getDamageMap(analysisId!);
      if (!result.ok) throw new Error(result.error);
      return result.data;
    },
    enabled: analysisId !== null && enabled,
  });
}

export type { AnalysisCreateResponse, DamageAnalysis, DamageMapResponse };

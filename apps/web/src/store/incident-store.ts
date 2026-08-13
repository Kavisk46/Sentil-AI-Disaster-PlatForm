import { create } from "zustand";
import type { GeographicCoordinate } from "@sentinelai/shared";

/**
 * Global, client-only state genuinely shared across otherwise-unrelated
 * parts of the command center: the map (which draws the selected route
 * points and reports map clicks), the analysis controls panel (which
 * shows/clears them), and the route comparison panel (which requests a
 * route between them) all need the same two values. Everything else
 * (server data) stays in TanStack Query — this store never holds fetched
 * API data itself, only the identifiers/selections used to *ask* for it.
 */
interface IncidentState {
  activeAnalysisId: string | null;
  setActiveAnalysisId: (id: string | null) => void;

  /** Explicitly separate from real API data — see `lib/demo/demo-data.ts`. */
  isDemoMode: boolean;
  setDemoMode: (enabled: boolean) => void;

  routeStart: GeographicCoordinate | null;
  routeDestination: GeographicCoordinate | null;
  setRoutePoint: (kind: "start" | "destination", point: GeographicCoordinate) => void;
  clearRoutePoints: () => void;
}

export const useIncidentStore = create<IncidentState>((set) => ({
  activeAnalysisId: null,
  setActiveAnalysisId: (id) =>
    set({ activeAnalysisId: id, routeStart: null, routeDestination: null }),

  isDemoMode: false,
  setDemoMode: (enabled) => set({ isDemoMode: enabled }),

  routeStart: null,
  routeDestination: null,
  setRoutePoint: (kind, point) =>
    set(kind === "start" ? { routeStart: point } : { routeDestination: point }),
  clearRoutePoints: () => set({ routeStart: null, routeDestination: null }),
}));

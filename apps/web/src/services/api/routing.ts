import type {
  ApiResult,
  GeographicCoordinate,
  RouteComparison,
  RouteResult,
} from "@sentinelai/shared";

import { apiPost } from "@/lib/api-client";
import { computeRouteComparison } from "@/lib/geo";

/** Typed client for `POST /api/v1/routing`. */

export function computeRoute(
  analysisId: string,
  start: GeographicCoordinate,
  destination: GeographicCoordinate,
  mode: "distance_only" | "risk_aware",
): Promise<ApiResult<RouteResult>> {
  return apiPost<RouteResult>("/api/v1/routing", {
    analysis_id: analysisId,
    start,
    destination,
    mode,
  });
}

/**
 * Fetches both routing modes for the same start/destination and derives a
 * `RouteComparison` client-side (see `lib/geo.ts::computeRouteComparison`
 * for why — the backend never exposes a single comparison endpoint).
 * Fails as a whole (returns the first error encountered) if either mode's
 * request fails, since a comparison with only one side is not a
 * comparison.
 */
export async function compareRoutes(
  analysisId: string,
  start: GeographicCoordinate,
  destination: GeographicCoordinate,
): Promise<ApiResult<RouteComparison>> {
  const [distanceOnly, riskAware] = await Promise.all([
    computeRoute(analysisId, start, destination, "distance_only"),
    computeRoute(analysisId, start, destination, "risk_aware"),
  ]);

  if (!distanceOnly.ok) return distanceOnly;
  if (!riskAware.ok) return riskAware;

  return { ok: true, data: computeRouteComparison(distanceOnly.data, riskAware.data) };
}

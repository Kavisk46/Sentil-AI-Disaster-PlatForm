/** Mirrors `apps/api/app/routing/schemas.py` and
 * `apps/api/app/schemas/routing.py`. */

import type { GeoJsonPosition } from "./geojson";
import type { GeographicCoordinate, RoadEdge } from "./roads";

export type RoutingMode = "distance_only" | "risk_aware";

export interface AccessibilitySummary {
  open: number;
  restricted: number;
  blocked: number;
  unknown: number;
}

export interface RouteResult {
  routing_mode: RoutingMode;
  found: boolean;
  start_node: string | null;
  destination_node: string | null;
  node_sequence: string[];
  edge_sequence: RoadEdge[];
  /** Ordered (longitude, latitude) points along the route, one per visited node. */
  route_geometry: GeoJsonPosition[];
  total_distance: number | null;
  total_cost: number | null;
  accumulated_risk: number | null;
  number_of_edges: number;
  accessibility_summary: AccessibilitySummary;
  reason: string | null;
}

export interface RoutingRequest {
  analysis_id: string;
  start: GeographicCoordinate;
  destination: GeographicCoordinate;
  mode: RoutingMode;
}

/**
 * The frontend's own equivalent of the backend's `RouteComparison`
 * (`app/routing/schemas.py`) — not returned by any single endpoint (see
 * `docs/architecture/frontend.md`, "Route comparison"), so it is computed
 * client-side in `services/api/routing.ts` from two real
 * `POST /api/v1/routing` responses (`distance_only` + `risk_aware`),
 * using the exact same formulas the backend uses for the same fields.
 * Never hard-coded.
 */
export interface RouteComparison {
  distanceOnly: RouteResult;
  riskAware: RouteResult;
  /** `riskAware.total_distance - distanceOnly.total_distance` (meters). */
  distanceDifference: number | null;
  /** `riskAware.accumulated_risk - distanceOnly.accumulated_risk`. */
  riskDifference: number | null;
  routesDiffer: boolean;
  /** `riskAware.total_distance / distanceOnly.total_distance`. */
  detourRatio: number | null;
  /** `1 - riskAware.accumulated_risk / distanceOnly.accumulated_risk`, as a fraction. */
  riskReduction: number | null;
}

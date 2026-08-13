/**
 * Mirrors `apps/api/app/roads/schemas.py` and
 * `apps/api/app/schemas/roads.py` — the road-network graph and its
 * per-edge risk/accessibility annotations.
 *
 * Road risk and road accessibility are deliberately two separate fields
 * here, matching the backend's own separation (`app/risk/__init__.py`,
 * "Accessibility is independent of risk") — a `critical`-risk edge is
 * never automatically `blocked`. The UI must always represent both, never
 * collapse one into the other.
 */

import type { DamageClass } from "./analysis";

export type AccessibilityStatus = "open" | "restricted" | "blocked" | "unknown";

export type RiskLevel = "low" | "moderate" | "high" | "critical";

export interface GeographicCoordinate {
  latitude: number;
  longitude: number;
}

export interface RiskSource {
  building_id: string;
  damage_class: DamageClass;
  confidence: number;
  distance_meters: number;
  contribution: number;
}

export interface RoadEdge {
  source_node: string;
  target_node: string;
  distance: number;
  base_cost: number;
  road_type: string | null;
  name: string | null;
  maxspeed: string | null;
  lanes: number | null;
  one_way: boolean;
  surface: string | null;
  accessibility: AccessibilityStatus;
  risk_score: number | null;
  risk_level: RiskLevel | null;
  risk_sources: RiskSource[];
}

/** An axis-aligned box `(x_min, y_min, x_max, y_max)` — mirrors
 * `app.ml.geospatial.geometry.BoundingBoxGeometry`. In WGS84 contexts,
 * `x` is longitude and `y` is latitude. */
export interface BoundingBoxGeometry {
  type: "bounding_box";
  coordinates: [x_min: number, y_min: number, x_max: number, y_max: number];
}

export interface RoadNetworkStatusResponse {
  loaded: boolean;
  node_count: number;
  edge_count: number;
  bounds: BoundingBoxGeometry | null;
  message: string | null;
}

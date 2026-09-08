/**
 * Mirrors `apps/api/app/intelligence/schemas.py` and
 * `apps/api/app/schemas/intelligence.py` — the Disaster Intelligence Core
 * domain model (F2) and its route-facing response contracts.
 *
 * `Geometry` completes the `PointGeometry`/`PolygonGeometry`/
 * `BoundingBoxGeometry` union `app.ml.geospatial.geometry` defines —
 * `BoundingBoxGeometry` itself already has a correct mirror in
 * `./roads.ts` (used by `RoadNetworkStatusResponse.bounds`), reused here
 * rather than duplicated; only the two missing variants are defined in
 * this file.
 *
 * `CoordinateReferenceSystemCode` (`"IMAGE" | "EPSG:4326"`) matches the
 * backend's actual serialized `CoordinateReferenceSystem` enum values
 * exactly (`app/ml/geospatial/crs.py`). Note: `./analysis.ts`'s
 * `CoordinateReferenceSystemName` (`"image" | "wgs84"`) is a pre-existing,
 * out-of-scope mismatch with those real runtime values — not fixed here
 * (unrelated file) and not reused, so this new code doesn't inherit it.
 *
 * Every entity below carries `is_simulated: boolean` — the mechanism that
 * guarantees demo/synthetic data (`app.intelligence.demo_scenario`) is
 * never presented as live information. No numeric `confidence` appears
 * anywhere in this file except where the backend genuinely allows one
 * (`Uncertainty.confidence`, `HazardPrediction.probability`) — both
 * `number | null`, and in this milestone always `null` in practice (no
 * calibrated model exists yet — see `HazardPrediction`'s doc comment).
 */

import type { DamageClass } from "./analysis";
import type { AccessibilityStatus, BoundingBoxGeometry } from "./roads";
import type { RouteResult } from "./routing";

export type CoordinateReferenceSystemCode = "IMAGE" | "EPSG:4326";

export interface PointGeometry {
  type: "point";
  coordinates: [number, number];
}

export interface PolygonGeometry {
  type: "polygon";
  coordinates: [number, number][][];
}

export type Geometry = PointGeometry | PolygonGeometry | BoundingBoxGeometry;

export type UncertaintyLevel = "low" | "moderate" | "high" | "unknown";

/** `confidence` is only ever non-null when a real, calibrated model
 * produced it — never fabricated to fill the field. */
export interface Uncertainty {
  level: UncertaintyLevel;
  confidence: number | null;
  reason: string;
  missing_information: string[];
  source_limitations: string[];
}

export type EvidenceSourceType =
  | "observation"
  | "damage_analysis"
  | "road_risk_analysis"
  | "routing_result"
  | "resource_registry"
  | "demo_scenario";

/** Recommendation -> Evidence -> Observation, never an unexplained AI output. */
export interface Evidence {
  id: string;
  source_type: EvidenceSourceType;
  observation_id: string | null;
  source: string;
  originating_subsystem: string;
  timestamp: string;
  summary: string;
  data_ref: string | null;
}

export type DisasterType =
  | "earthquake"
  | "flood"
  | "hurricane"
  | "wildfire"
  | "landslide"
  | "tsunami"
  | "structural_collapse"
  | "other";

export type DisasterStatus =
  | "reported"
  | "active"
  | "response_in_progress"
  | "contained"
  | "closed";

export interface Disaster {
  id: string;
  type: DisasterType;
  label: string;
  status: DisasterStatus;
  location: Geometry | null;
  location_crs: CoordinateReferenceSystemCode;
  start_time: string | null;
  source: string;
  is_simulated: boolean;
  provenance: string;
}

export type ObservationType =
  | "satellite_image"
  | "drone_image"
  | "road_obstruction_report"
  | "infrastructure_damage_report"
  | "emergency_report"
  | "damage_detection";

/** An Observation is NOT a prediction — see `HazardPrediction`. */
export interface Observation {
  id: string;
  type: ObservationType;
  source: string;
  timestamp: string;
  geometry: Geometry | null;
  geometry_crs: CoordinateReferenceSystemCode;
  value_ref: string;
  evidence: Evidence;
  uncertainty: Uncertainty;
  is_simulated: boolean;
}

export interface AffectedArea {
  id: string;
  geometry: Geometry;
  geometry_crs: CoordinateReferenceSystemCode;
  damage_level: DamageClass;
  /** Only ever set from a real population source — never estimated. */
  affected_population: number | null;
  accessibility: AccessibilityStatus | null;
  evidence: Evidence[];
  uncertainty: Uncertainty;
  is_simulated: boolean;
}

export type SearchPriorityLevel = "low" | "moderate" | "high" | "critical";

export interface SearchZoneFactor {
  name: string;
  value: number;
  weight: number;
  contribution: number;
  description: string;
}

/**
 * A candidate area for search/rescue investigation — NEVER a claim a
 * person is located here. Always present as "high-priority search zone
 * based on available evidence." See
 * `apps/api/app/intelligence/search_priority.py`.
 */
export interface SearchZone {
  id: string;
  geometry: Geometry;
  geometry_crs: CoordinateReferenceSystemCode;
  priority_score: number;
  priority_level: SearchPriorityLevel;
  factors: SearchZoneFactor[];
  missing_factors: string[];
  reasons: string[];
  supporting_observations: string[];
  supporting_evidence: Evidence[];
  uncertainty: Uncertainty;
  is_simulated: boolean;
}

export type HazardType =
  | "flood"
  | "landslide"
  | "structural_collapse"
  | "blocked_road"
  | "damaged_bridge"
  | "wildfire"
  | "tsunami"
  | "earthquake_aftershock"
  | "other";

export type HazardSeverity = "low" | "moderate" | "high" | "critical" | "unknown";

export interface Hazard {
  id: string;
  type: HazardType;
  severity: HazardSeverity;
  geometry: Geometry;
  geometry_crs: CoordinateReferenceSystemCode;
  source: string;
  timestamp: string;
  evidence: Evidence[];
  uncertainty: Uncertainty;
  is_simulated: boolean;
}

export type ResourceType =
  | "rescue_team"
  | "drone"
  | "helicopter"
  | "ambulance"
  | "excavator"
  | "medical_team"
  | "communication_unit"
  | "other";

/** A closed, coarse vocabulary — exact-match, not fuzzy string matching. */
export type ResourceCapability =
  | "aerial_recon"
  | "ground_search"
  | "water_rescue"
  | "medical_triage"
  | "heavy_lifting"
  | "structural_assessment"
  | "transport"
  | "communications_relay";

export type ResourceAvailability = "available" | "deployed" | "unavailable" | "unknown";

export interface OperationalConstraint {
  description: string;
  blocking: boolean;
}

export interface Resource {
  id: string;
  type: ResourceType;
  capabilities: ResourceCapability[];
  location: Geometry | null;
  location_crs: CoordinateReferenceSystemCode;
  availability: ResourceAvailability;
  capacity: number | null;
  operational_constraints: OperationalConstraint[];
  is_simulated: boolean;
}

export type TerrainCapability =
  | "urban"
  | "mountainous"
  | "flooded"
  | "collapsed_structure"
  | "water";

/** Composition, not duplication: `resource` carries every field a
 * non-human asset also has. */
export interface RescueTeam {
  resource: Resource;
  personnel_count: number;
  skills: ResourceCapability[];
  equipment: string[];
  medical_capability: boolean;
  terrain_capabilities: TerrainCapability[];
}

export type InfrastructureType =
  | "road"
  | "bridge"
  | "hospital"
  | "helipad"
  | "shelter"
  | "tunnel"
  | "communication_station"
  | "other";

export type InfrastructureStatus = "operational" | "degraded" | "non_operational" | "unknown";

export interface Infrastructure {
  id: string;
  type: InfrastructureType;
  geometry: Geometry;
  geometry_crs: CoordinateReferenceSystemCode;
  status: InfrastructureStatus;
  accessibility: AccessibilityStatus | null;
  evidence: Evidence[];
  uncertainty: Uncertainty;
  is_simulated: boolean;
}

/**
 * Reuses the real routing engine's own `RouteResult` (`./routing.ts`)
 * rather than reinventing pathfinding. `estimated_time_seconds` is
 * always `null` — the routing engine has no speed/travel-time model, so
 * this is never derived from an assumed speed.
 */
export interface Route {
  id: string;
  origin: Geometry;
  destination: Geometry;
  result: RouteResult;
  estimated_time_seconds: number | null;
  blocking_hazards: string[];
  provenance: string;
}

/** `"unavailable"` is the only status F2 can ever produce — no
 * predictive hazard model exists in this milestone. */
export type HazardPredictionStatus = "unavailable" | "available";

export interface HazardPrediction {
  prediction_id: string;
  hazard_type: HazardType;
  target_area: Geometry;
  forecast_window_start: string;
  forecast_window_end: string;
  status: HazardPredictionStatus;
  /** Only ever set by a real, calibrated model. `null` when status is `"unavailable"`. */
  probability: number | null;
  severity: HazardSeverity | null;
  model_source: string | null;
  evidence: Evidence[];
  uncertainty: Uncertainty;
}

/** A closed, deterministic vocabulary — every recommendation is
 * traceable to the exact rule that produced it, never free text. */
export type RecommendationAction =
  | "deploy_drone_recon"
  | "deploy_ground_search_team"
  | "deploy_medical_team"
  | "inspect_infrastructure_before_dispatch"
  | "avoid_route_due_to_hazard"
  | "escalate_for_additional_resources"
  | "hold_pending_more_information";

export type RecommendationPriority = "low" | "moderate" | "high" | "critical";

export interface Recommendation {
  id: string;
  action: RecommendationAction;
  target_id: string;
  target_description: string;
  priority: RecommendationPriority;
  rationale: string;
  required_capabilities: ResourceCapability[];
  supporting_evidence: Evidence[];
  uncertainty: Uncertainty;
  limitations: string[];
  is_simulated: boolean;
}

export type ReachabilityStatus = "reachable" | "unreachable" | "unknown";

/** NOT one of the 13 core domain entities — the computed, explainable
 * output of `app.intelligence.capability_matching`. Keeps the four
 * questions (can perform / is available / can reach / route operational)
 * as separate fields, never collapsed into one opaque score. */
export interface CapabilityMatchResult {
  resource_id: string;
  can_perform_task: boolean;
  missing_capabilities: ResourceCapability[];
  is_available: boolean;
  distance_meters: number | null;
  reachability: ReachabilityStatus;
  route_operational: boolean | null;
  eligible: boolean;
  match_score: number;
  rationale: string[];
  is_simulated: boolean;
}

// --- Route-facing response contracts (app/schemas/intelligence.py) --------

export interface DisasterSummaryResponse {
  disaster: Disaster;
  observation_count: number;
  affected_area_count: number;
  hazard_count: number;
  resource_count: number;
  infrastructure_count: number;
  route_count: number;
}

export interface SearchZoneListResponse {
  disaster_id: string;
  search_zones: SearchZone[];
}

export interface ResourceListResponse {
  disaster_id: string;
  resources: Resource[];
}

export interface RecommendationListResponse {
  disaster_id: string;
  recommendations: Recommendation[];
}

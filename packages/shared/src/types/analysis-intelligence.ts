/**
 * Mirrors `apps/api/app/schemas/analysis_intelligence.py` — the F3
 * analysis-aware intelligence route contracts
 * (`GET /api/v1/analysis/{analysis_id}/intelligence[...]`).
 *
 * Distinct from `./intelligence.ts` (F2's disaster-scoped contracts,
 * unchanged by F3): this file's responses are keyed by the existing
 * `analysis_id`, carry a *derived* (not stored) `disaster_id` — see
 * `app.intelligence.analysis_adapter.derive_disaster_id` — and always
 * report `is_simulated: false` for the analysis-derived entities
 * themselves (only the resource pool is `resources_are_demo: true`, since
 * no real resource-ingestion system exists yet).
 */

import type { CapabilityMatchResult, Recommendation, SearchZone } from "./intelligence";
import type { RouteResult } from "./routing";

export type RouteFeasibilityStatusCode = "computed" | "route_unavailable" | "not_applicable";

/** Whether a real route was actually computed for a capability-match
 * candidate, and why not when it wasn't — never a fabricated route. */
export interface RouteFeasibilityStatus {
  status: RouteFeasibilityStatusCode;
  reason: string | null;
}

export interface AnalysisCapabilityMatch {
  match: CapabilityMatchResult;
  route: RouteResult | null;
  route_feasibility: RouteFeasibilityStatus;
}

export interface AnalysisIntelligenceContextResponse {
  analysis_id: string;
  disaster_id: string;
  context_available: boolean;
  context_unavailable_reason: string | null;
  is_simulated: boolean;
  affected_area_count: number;
  hazard_count: number;
  infrastructure_count: number;
  roads_available: boolean;
  roads_unavailable_reason: string | null;
  resources_available: boolean;
  resources_are_demo: boolean;
}

export interface AnalysisSearchZonesResponse {
  analysis_id: string;
  disaster_id: string;
  context_available: boolean;
  context_unavailable_reason: string | null;
  search_zones: SearchZone[];
}

/** Bundles ranked recommendations with resource-capability-match detail
 * for the single top-priority search zone — directly serving "What can
 * reach it?" without a 4th/5th endpoint. */
export interface AnalysisRecommendationsResponse {
  analysis_id: string;
  disaster_id: string;
  context_available: boolean;
  context_unavailable_reason: string | null;
  recommendations: Recommendation[];
  top_search_zone_id: string | null;
  resource_candidates: AnalysisCapabilityMatch[];
  resources_are_demo: boolean;
  roads_available: boolean;
  roads_unavailable_reason: string | null;
}

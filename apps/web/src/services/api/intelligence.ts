import type {
  ApiResult,
  DisasterSummaryResponse,
  RecommendationListResponse,
  ResourceListResponse,
  SearchZoneListResponse,
} from "@sentinelai/shared";

import { apiGet } from "@/lib/api-client";

/**
 * Typed client for the Disaster Intelligence Core (F2):
 * `GET /api/v1/intelligence/{disaster_id}[/search-zones|/resources|/recommendations]`.
 * Kept UI-free — consumed only by `hooks/use-intelligence.ts`, never
 * called directly from a component (see
 * `docs/architecture/frontend.md`, "API integration").
 *
 * Not yet wired into any dashboard panel — `disaster_id` is a distinct
 * identifier from the existing command center's `activeAnalysisId`
 * (an "analysis" and a "disaster" are different concepts in this
 * backend; see `apps/api/app/api/v1/endpoints/intelligence.py`'s doc
 * comment), so there is no existing panel this data naturally slots
 * into yet. This file exists so a future milestone's UI work has typed,
 * tested plumbing ready to build on, per this milestone's brief ("add
 * the minimum typed data plumbing required for future integration").
 */

export function getDisasterSummary(disasterId: string): Promise<ApiResult<DisasterSummaryResponse>> {
  return apiGet<DisasterSummaryResponse>(`/api/v1/intelligence/${disasterId}`);
}

export function getSearchZones(disasterId: string): Promise<ApiResult<SearchZoneListResponse>> {
  return apiGet<SearchZoneListResponse>(`/api/v1/intelligence/${disasterId}/search-zones`);
}

export function getIntelligenceResources(
  disasterId: string,
): Promise<ApiResult<ResourceListResponse>> {
  return apiGet<ResourceListResponse>(`/api/v1/intelligence/${disasterId}/resources`);
}

export function getRecommendations(
  disasterId: string,
): Promise<ApiResult<RecommendationListResponse>> {
  return apiGet<RecommendationListResponse>(`/api/v1/intelligence/${disasterId}/recommendations`);
}

/** Mirrors `apps/api/app/incident/schemas.py` and
 * `apps/api/app/schemas/incident.py` — the AI incident briefing contract
 * (Milestone 7). `IncidentBriefing.source` distinguishes an actual LLM
 * ("provider") from the deterministic template fallback ("fallback") —
 * both are equally "AI-generated" from the UI's point of view (neither is
 * human-authored), so the UI should label both the same way, not imply
 * "provider" is more authoritative. */

import type { GeographicCoordinate } from "./roads";

export type IncidentSeverity = "low" | "moderate" | "high" | "critical" | "unknown";

export type ConfidenceLevel = "low" | "moderate" | "high" | "unknown";

export interface AffectedStructuresSummary {
  total: number;
  damaged: number;
  severely_damaged: number;
  destroyed: number;
  high_priority_count: number;
}

export interface IncidentBriefing {
  analysis_id: string;
  incident_severity: IncidentSeverity;
  affected_structures: AffectedStructuresSummary;
  priority_area: string;
  route_summary: string;
  key_findings: string[];
  limitations: string[];
  confidence: ConfidenceLevel;
  generated_at: string;
  source: "provider" | "fallback";
  prompt_version: string;
  disclaimer: string;
}

export interface RouteQuery {
  start: GeographicCoordinate;
  destination: GeographicCoordinate;
}

export interface IncidentSummaryRequest {
  route?: RouteQuery;
}

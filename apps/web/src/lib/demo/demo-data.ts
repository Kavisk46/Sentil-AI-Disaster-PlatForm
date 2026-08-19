import type {
  DamageMapResponse,
  DamageSummary,
  IncidentBriefing,
  RoadRiskResponse,
  RouteResult,
} from "@sentinelai/shared";

import { computeRouteComparison } from "@/lib/geo";

/**
 * DEMO MODE fixtures — static, hand-authored sample data used only when a
 * user explicitly enables the "Demo mode" toggle (see
 * `store/incident-store.ts`), so the command center's fully-populated
 * layout can be exercised during frontend development without a running
 * backend or a real disaster image. Never imported by a data-fetching
 * hook, and never used as a silent fallback when a real API call fails —
 * see `components/command-center/command-center.tsx`, which branches on
 * `isDemoMode` *before* any hook runs, and the always-visible "DEMO MODE"
 * banner that accompanies it.
 *
 * All coordinates are centered on a deliberately fictional origin (a point
 * in open ocean, not any real city or region) so this data can never be
 * mistaken for a real place or a real event.
 */

export const DEMO_ANALYSIS_ID = "00000000-0000-0000-0000-000000000demo";

/** A fictional point in open ocean — not any real place. */
const ORIGIN = { lat: 1.5, lon: 1.5 };

export const DEMO_DAMAGE_MAP: DamageMapResponse = {
  analysis_id: DEMO_ANALYSIS_ID,
  status: "completed",
  available: true,
  reason: null,
  feature_collection: {
    type: "FeatureCollection",
    coordinate_reference_system: "EPSG:4326",
    features: [
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [ORIGIN.lon, ORIGIN.lat] },
        properties: {
          building_id: "demo-b0",
          damage_class: "destroyed",
          confidence: 0.91,
          priority: "critical",
          georeferenced: true,
        },
      },
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [ORIGIN.lon + 0.004, ORIGIN.lat + 0.002] },
        properties: {
          building_id: "demo-b1",
          damage_class: "destroyed",
          confidence: 0.86,
          priority: "critical",
          georeferenced: true,
        },
      },
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [ORIGIN.lon - 0.003, ORIGIN.lat + 0.003] },
        properties: {
          building_id: "demo-b2",
          damage_class: "major",
          confidence: 0.78,
          priority: "high",
          georeferenced: true,
        },
      },
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [ORIGIN.lon + 0.006, ORIGIN.lat - 0.003] },
        properties: {
          building_id: "demo-b3",
          damage_class: "major",
          confidence: 0.73,
          priority: "high",
          georeferenced: true,
        },
      },
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [ORIGIN.lon - 0.005, ORIGIN.lat - 0.004] },
        properties: {
          building_id: "demo-b4",
          damage_class: "minor",
          confidence: 0.68,
          priority: "medium",
          georeferenced: true,
        },
      },
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [ORIGIN.lon + 0.001, ORIGIN.lat + 0.006] },
        properties: {
          building_id: "demo-b5",
          damage_class: "no_damage",
          confidence: 0.95,
          priority: "low",
          georeferenced: true,
        },
      },
    ],
  },
};

/** Matches `DEMO_DAMAGE_MAP`'s six features (2 destroyed, 2 major, 1
 * minor, 1 no_damage), computed the same way the backend's own
 * `DamageSummary` is (`severely_damaged` = major + destroyed). */
export const DEMO_DAMAGE_SUMMARY: DamageSummary = {
  total_buildings: 6,
  damaged_buildings: 5,
  severely_damaged: 4,
  destroyed: 2,
};

export const DEMO_ROAD_RISK: RoadRiskResponse = {
  analysis_id: DEMO_ANALYSIS_ID,
  status: "completed",
  available: true,
  reason: null,
  edges: [
    {
      source_node: "n1",
      target_node: "n2",
      distance: 420,
      base_cost: 420,
      road_type: "residential",
      name: "Demo Coastal Rd",
      maxspeed: null,
      lanes: null,
      one_way: false,
      surface: null,
      accessibility: "blocked",
      risk_score: 0.92,
      risk_level: "critical",
      risk_sources: [
        {
          building_id: "demo-b0",
          damage_class: "destroyed",
          confidence: 0.91,
          distance_meters: 18,
          contribution: 0.92,
        },
      ],
    },
    {
      source_node: "n2",
      target_node: "n3",
      distance: 310,
      base_cost: 310,
      road_type: "residential",
      name: "Demo 2nd St",
      maxspeed: null,
      lanes: null,
      one_way: false,
      surface: null,
      accessibility: "restricted",
      risk_score: 0.61,
      risk_level: "high",
      risk_sources: [
        {
          building_id: "demo-b2",
          damage_class: "major",
          confidence: 0.78,
          distance_meters: 40,
          contribution: 0.61,
        },
      ],
    },
    {
      source_node: "n3",
      target_node: "n4",
      distance: 260,
      base_cost: 260,
      road_type: "residential",
      name: "Demo Market Ave",
      maxspeed: null,
      lanes: null,
      one_way: false,
      surface: null,
      accessibility: "open",
      risk_score: 0.18,
      risk_level: "low",
      risk_sources: [],
    },
    {
      source_node: "n1",
      target_node: "n5",
      distance: 540,
      base_cost: 540,
      road_type: "secondary",
      name: "Demo Bypass Rd",
      maxspeed: null,
      lanes: null,
      one_way: false,
      surface: null,
      accessibility: "open",
      risk_score: 0.05,
      risk_level: "low",
      risk_sources: [],
    },
    {
      source_node: "n5",
      target_node: "n4",
      distance: 480,
      base_cost: 480,
      road_type: "secondary",
      name: "Demo Ridge Rd",
      maxspeed: null,
      lanes: null,
      one_way: false,
      surface: null,
      accessibility: "open",
      risk_score: 0.09,
      risk_level: "low",
      risk_sources: [],
    },
  ],
};

const DISTANCE_ONLY_ROUTE: RouteResult = {
  routing_mode: "distance_only",
  found: true,
  start_node: "n1",
  destination_node: "n4",
  node_sequence: ["n1", "n2", "n3", "n4"],
  edge_sequence: [
    DEMO_ROAD_RISK.edges[0]!,
    DEMO_ROAD_RISK.edges[1]!,
    DEMO_ROAD_RISK.edges[2]!,
  ],
  route_geometry: [
    [ORIGIN.lon - 0.006, ORIGIN.lat - 0.002],
    [ORIGIN.lon - 0.001, ORIGIN.lat + 0.001],
    [ORIGIN.lon + 0.003, ORIGIN.lat + 0.0015],
    [ORIGIN.lon + 0.007, ORIGIN.lat + 0.001],
  ],
  total_distance: 990,
  total_cost: 990,
  accumulated_risk: 1.71,
  number_of_edges: 3,
  accessibility_summary: { open: 1, restricted: 1, blocked: 1, unknown: 0 },
  reason: null,
};

const RISK_AWARE_ROUTE: RouteResult = {
  routing_mode: "risk_aware",
  found: true,
  start_node: "n1",
  destination_node: "n4",
  node_sequence: ["n1", "n5", "n4"],
  edge_sequence: [DEMO_ROAD_RISK.edges[3]!, DEMO_ROAD_RISK.edges[4]!],
  route_geometry: [
    [ORIGIN.lon - 0.006, ORIGIN.lat - 0.002],
    [ORIGIN.lon - 0.002, ORIGIN.lat - 0.006],
    [ORIGIN.lon + 0.007, ORIGIN.lat + 0.001],
  ],
  total_distance: 1020,
  total_cost: 1020,
  accumulated_risk: 0.14,
  number_of_edges: 2,
  accessibility_summary: { open: 2, restricted: 0, blocked: 0, unknown: 0 },
  reason: null,
};

export const DEMO_ROUTES = {
  distanceOnly: DISTANCE_ONLY_ROUTE,
  riskAware: RISK_AWARE_ROUTE,
};

/** Derived the same way `services/api/routing.ts::compareRoutes` derives
 * a real comparison — see `lib/geo.ts::computeRouteComparison`. */
export const DEMO_ROUTE_COMPARISON = computeRouteComparison(DISTANCE_ONLY_ROUTE, RISK_AWARE_ROUTE);

export const DEMO_INCIDENT_BRIEFING: IncidentBriefing = {
  analysis_id: DEMO_ANALYSIS_ID,
  incident_severity: "high",
  affected_structures: {
    total: 6,
    damaged: 5,
    severely_damaged: 4,
    destroyed: 2,
    high_priority_count: 4,
  },
  priority_area:
    "4 high-priority structure(s) were identified, within the approximate bounding area " +
    "[1.50, 1.49] to [1.51, 1.51].",
  route_summary:
    "Compared to the shortest-distance baseline, the selected route covers 1020m, an " +
    "accumulated risk score of 0.14, versus a 990m shortest-distance baseline, avoiding 2 " +
    "high-risk segment(s).",
  key_findings: [
    "6 structure(s) assessed: 5 damaged, 2 destroyed.",
    "Average detection confidence: 0.82.",
    "2 of 5 assessed road segment(s) are at high or critical modeled risk; 1 segment(s) are " +
      "recorded as blocked, 1 as restricted.",
  ],
  limitations: [
    "Damage predictions may be inaccurate.",
    "Road risk is a modeled estimate based on proximity to detected damage, not a verified fact.",
    "Road accessibility (blocked/restricted) has not been independently confirmed.",
  ],
  confidence: "moderate",
  generated_at: "2026-01-01T00:00:00Z",
  source: "fallback",
  prompt_version: "incident_summary_v1",
  disclaimer:
    "This briefing is AI-assisted decision support, not a verified emergency assessment. " +
    "Damage predictions may be wrong. Road risk is a modeled estimate, not a confirmed fact. " +
    "Road accessibility has not been independently verified. Real emergency response " +
    "decisions must rely on authoritative, verified information — not this summary alone.",
};

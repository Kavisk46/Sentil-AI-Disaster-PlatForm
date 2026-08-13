import { describe, expect, it } from "vitest";
import type { RouteResult } from "@sentinelai/shared";

import {
  computeRouteComparison,
  formatDistanceMeters,
  formatPercent,
  formatRiskScore,
  routeToLineFeature,
  routeToRiskSegments,
} from "@/lib/geo";

function makeRoute(overrides: Partial<RouteResult>): RouteResult {
  return {
    routing_mode: "distance_only",
    found: true,
    start_node: "a",
    destination_node: "b",
    node_sequence: ["a", "b"],
    edge_sequence: [],
    route_geometry: [
      [0, 0],
      [1, 1],
    ],
    total_distance: 100,
    total_cost: 100,
    accumulated_risk: 1,
    number_of_edges: 1,
    accessibility_summary: { open: 1, restricted: 0, blocked: 0, unknown: 0 },
    reason: null,
    ...overrides,
  };
}

describe("computeRouteComparison", () => {
  it("derives distance/risk differences, detour ratio, and risk reduction from real route numbers", () => {
    const distanceOnly = makeRoute({ total_distance: 1000, accumulated_risk: 0.8 });
    const riskAware = makeRoute({
      routing_mode: "risk_aware",
      total_distance: 1200,
      accumulated_risk: 0.2,
    });

    const comparison = computeRouteComparison(distanceOnly, riskAware);

    expect(comparison.distanceDifference).toBe(200);
    expect(comparison.riskDifference).toBeCloseTo(-0.6);
    expect(comparison.detourRatio).toBeCloseTo(1.2);
    expect(comparison.riskReduction).toBeCloseTo(0.75);
  });

  it("never divides by zero — a zero-distance baseline yields a null detour ratio", () => {
    const distanceOnly = makeRoute({ total_distance: 0 });
    const riskAware = makeRoute({ total_distance: 50 });

    const comparison = computeRouteComparison(distanceOnly, riskAware);

    expect(comparison.detourRatio).toBeNull();
  });

  it("reports null differences when either route was not found", () => {
    const distanceOnly = makeRoute({ found: true });
    const riskAware = makeRoute({ found: false, total_distance: null, accumulated_risk: null });

    const comparison = computeRouteComparison(distanceOnly, riskAware);

    expect(comparison.distanceDifference).toBeNull();
    expect(comparison.riskDifference).toBeNull();
    expect(comparison.detourRatio).toBeNull();
    expect(comparison.riskReduction).toBeNull();
  });
});

describe("routeToLineFeature", () => {
  it("returns null for a route that was not found", () => {
    expect(routeToLineFeature(makeRoute({ found: false }))).toBeNull();
  });

  it("returns null for fewer than 2 geometry points", () => {
    expect(routeToLineFeature(makeRoute({ route_geometry: [[0, 0]] }))).toBeNull();
  });

  it("builds a LineString feature carrying the routing mode", () => {
    const feature = routeToLineFeature(makeRoute({ routing_mode: "risk_aware" }));
    expect(feature?.geometry.type).toBe("LineString");
    expect(feature?.properties.mode).toBe("risk_aware");
  });
});

describe("routeToRiskSegments", () => {
  it("pairs each edge with its own risk level from real edge_sequence data", () => {
    const route = makeRoute({
      route_geometry: [
        [0, 0],
        [1, 0],
        [2, 0],
      ],
      edge_sequence: [
        {
          source_node: "a",
          target_node: "b",
          distance: 1,
          base_cost: 1,
          road_type: null,
          name: null,
          maxspeed: null,
          lanes: null,
          one_way: false,
          surface: null,
          accessibility: "open",
          risk_score: 0.1,
          risk_level: "low",
          risk_sources: [],
        },
        {
          source_node: "b",
          target_node: "c",
          distance: 1,
          base_cost: 1,
          road_type: null,
          name: null,
          maxspeed: null,
          lanes: null,
          one_way: false,
          surface: null,
          accessibility: "blocked",
          risk_score: 0.9,
          risk_level: "critical",
          risk_sources: [],
        },
      ],
    });

    const segments = routeToRiskSegments(route);

    expect(segments).toHaveLength(2);
    expect(segments[0]?.properties.riskLevel).toBe("low");
    expect(segments[1]?.properties.riskLevel).toBe("critical");
  });

  it("yields no segments when geometry/edge counts don't line up (unusable data)", () => {
    const route = makeRoute({
      route_geometry: [
        [0, 0],
        [1, 0],
      ],
      edge_sequence: [],
    });
    expect(routeToRiskSegments(route)).toHaveLength(0);
  });
});

describe("formatters", () => {
  it("formats distance in km above 1000m and meters below", () => {
    expect(formatDistanceMeters(4200)).toBe("4.2 km");
    expect(formatDistanceMeters(850)).toBe("850 m");
    expect(formatDistanceMeters(null)).toBe("—");
  });

  it("formats risk scores to 2 decimal places", () => {
    expect(formatRiskScore(0.812)).toBe("0.81");
    expect(formatRiskScore(null)).toBe("—");
  });

  it("formats fractions as percentages", () => {
    expect(formatPercent(0.617)).toBe("61.7%");
    expect(formatPercent(null)).toBe("—");
  });
});

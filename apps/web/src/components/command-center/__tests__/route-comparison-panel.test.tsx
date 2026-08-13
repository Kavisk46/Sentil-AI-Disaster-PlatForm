import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RouteResult } from "@sentinelai/shared";

import { RouteComparisonPanel } from "@/components/command-center/route-comparison-panel";
import { computeRouteComparison } from "@/lib/geo";

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
    total_distance: 4200,
    total_cost: 4200,
    accumulated_risk: 0.81,
    number_of_edges: 1,
    accessibility_summary: { open: 1, restricted: 0, blocked: 0, unknown: 0 },
    reason: null,
    ...overrides,
  };
}

describe("RouteComparisonPanel", () => {
  it("prompts for point selection before any route has been requested", () => {
    render(
      <RouteComparisonPanel
        comparison={null}
        hasSelectedPoints={false}
        isLoading={false}
        isError={false}
      />,
    );
    expect(screen.getByText(/click the map to set a start and destination/i)).toBeInTheDocument();
  });

  it("renders distance/risk numbers computed from real RouteResult data, not hard-coded", () => {
    const distanceOnly = makeRoute({ total_distance: 4200, accumulated_risk: 0.81 });
    const riskAware = makeRoute({
      routing_mode: "risk_aware",
      total_distance: 4800,
      accumulated_risk: 0.31,
    });
    const comparison = computeRouteComparison(distanceOnly, riskAware);

    render(
      <RouteComparisonPanel
        comparison={comparison}
        hasSelectedPoints={true}
        isLoading={false}
        isError={false}
      />,
    );

    expect(screen.getByText("4.2 km")).toBeInTheDocument();
    expect(screen.getByText("4.8 km")).toBeInTheDocument();
    expect(screen.getByText("Risk: 0.81")).toBeInTheDocument();
    expect(screen.getByText("Risk: 0.31")).toBeInTheDocument();
    // riskReduction = 1 - 0.31/0.81 ≈ 61.7%
    expect(screen.getByText("61.7%")).toBeInTheDocument();
  });

  it("shows an error state when the routing request failed", () => {
    render(
      <RouteComparisonPanel
        comparison={null}
        hasSelectedPoints={true}
        isLoading={false}
        isError={true}
        errorMessage="No road network is loaded."
      />,
    );
    expect(screen.getByText("Route unavailable")).toBeInTheDocument();
    expect(screen.getByText("No road network is loaded.")).toBeInTheDocument();
  });
});

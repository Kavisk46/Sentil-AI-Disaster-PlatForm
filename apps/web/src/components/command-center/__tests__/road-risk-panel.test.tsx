import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RoadEdge } from "@sentinelai/shared";

import { RoadRiskPanel } from "@/components/command-center/road-risk-panel";

const edges: RoadEdge[] = [
  {
    source_node: "n1",
    target_node: "n2",
    distance: 100,
    base_cost: 100,
    road_type: null,
    name: "Main St",
    maxspeed: null,
    lanes: null,
    one_way: false,
    surface: null,
    accessibility: "blocked",
    risk_score: 0.9,
    risk_level: "critical",
    risk_sources: [],
  },
];

describe("RoadRiskPanel", () => {
  it("renders risk level and accessibility as two distinct badges for the same edge", () => {
    render(
      <RoadRiskPanel
        edges={edges}
        available={true}
        reason={null}
        isLoading={false}
        isError={false}
      />,
    );

    const row = screen.getByText("Main St").closest("li")!;
    // Non-color indicators: risk shows its short code, accessibility shows a
    // different short code — never the same badge or the same word.
    expect(row).toHaveTextContent("C"); // critical risk code
    expect(row).toHaveTextContent("BLKD"); // blocked accessibility code
  });

  it("shows a clear empty state with the real backend reason", () => {
    render(
      <RoadRiskPanel
        edges={[]}
        available={false}
        reason="No road network is loaded (see GET /api/v1/roads/status)."
        isLoading={false}
        isError={false}
      />,
    );

    expect(
      screen.getByText("No road network is loaded (see GET /api/v1/roads/status)."),
    ).toBeInTheDocument();
  });

  it("shows an error state for a backend failure", () => {
    render(
      <RoadRiskPanel
        edges={[]}
        available={false}
        reason={null}
        isLoading={false}
        isError={true}
        errorMessage="503 Service Unavailable"
      />,
    );

    expect(screen.getByText("Road risk data unavailable")).toBeInTheDocument();
  });
});

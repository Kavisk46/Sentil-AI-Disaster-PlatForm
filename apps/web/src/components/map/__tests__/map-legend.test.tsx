import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MapLegend } from "@/components/map/map-legend";

describe("MapLegend", () => {
  it("always shows the damage, route, and search-priority sections", () => {
    render(<MapLegend />);
    expect(screen.getByText("Damage")).toBeInTheDocument();
    expect(screen.getByText("Route")).toBeInTheDocument();
    expect(screen.getByText("Search priority")).toBeInTheDocument();
  });

  it("hides the Resources section when no resource markers are plotted", () => {
    render(<MapLegend showResources={false} />);
    expect(screen.queryByText("Resources")).not.toBeInTheDocument();
  });

  it("shows the Resources section when resource markers are plotted", () => {
    render(<MapLegend showResources={true} />);
    expect(screen.getByText("Resources")).toBeInTheDocument();
    expect(screen.getByText("Available")).toBeInTheDocument();
  });

  it("hides the hazards/infrastructure disclosure when neither count is known", () => {
    render(<MapLegend hazardCount={null} infrastructureCount={null} />);
    expect(screen.queryByText("Hazards & infrastructure")).not.toBeInTheDocument();
  });

  it("discloses hazard/infrastructure counts honestly as not mapped, never as fake pins", () => {
    render(<MapLegend hazardCount={2} infrastructureCount={1} />);
    expect(screen.getByText("Hazards & infrastructure")).toBeInTheDocument();
    expect(screen.getByText(/2 hazard\(s\), 1 infrastructure record\(s\)/)).toBeInTheDocument();
    expect(screen.getByText(/not shown on the map \(no geometry available\)/)).toBeInTheDocument();
  });

  it("shows a zero count honestly rather than hiding it", () => {
    render(<MapLegend hazardCount={0} infrastructureCount={3} />);
    expect(screen.getByText(/0 hazard\(s\), 3 infrastructure record\(s\)/)).toBeInTheDocument();
  });
});

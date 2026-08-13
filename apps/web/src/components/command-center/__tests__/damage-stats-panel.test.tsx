import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DamageSummary } from "@sentinelai/shared";

import { DamageStatsPanel } from "@/components/command-center/damage-stats-panel";

const summary: DamageSummary = {
  total_buildings: 10,
  damaged_buildings: 7,
  severely_damaged: 4,
  destroyed: 2,
};

describe("DamageStatsPanel", () => {
  it("renders derived per-class counts from a real DamageSummary", () => {
    render(
      <DamageStatsPanel
        summary={summary}
        available={true}
        reason={null}
        highPriorityCount={3}
        isLoading={false}
        isError={false}
      />,
    );

    expect(screen.getByText("10")).toBeInTheDocument(); // total
    // no_damage=3, minor=3, major=2, destroyed=2 — assert the destroyed count renders.
    const destroyedRow = screen.getByText("Destroyed").closest("li");
    expect(destroyedRow).toHaveTextContent("2");
    expect(screen.getByText(/high-priority structure\(s\) identified\.$/)).toHaveTextContent(
      "3 high-priority structure(s) identified.",
    );
  });

  it("shows a clear empty state when unavailable, with the real reason text", () => {
    render(
      <DamageStatsPanel
        summary={null}
        available={false}
        reason="Analysis is not completed yet (status=processing)."
        highPriorityCount={null}
        isLoading={false}
        isError={false}
      />,
    );

    expect(screen.getByText("Analysis is not completed yet (status=processing).")).toBeInTheDocument();
  });

  it("shows an error state without a stack trace when the backend is unreachable", () => {
    render(
      <DamageStatsPanel
        summary={null}
        available={false}
        reason={null}
        highPriorityCount={null}
        isLoading={false}
        isError={true}
        errorMessage="Failed to fetch"
      />,
    );

    expect(screen.getByText("Damage data unavailable")).toBeInTheDocument();
    expect(screen.getByText("Failed to fetch")).toBeInTheDocument();
  });
});

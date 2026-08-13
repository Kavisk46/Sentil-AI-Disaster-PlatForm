import { describe, expect, it } from "vitest";
import type { DamageSummary } from "@sentinelai/shared";

import { deriveDamageBreakdown } from "@/lib/damage";

describe("deriveDamageBreakdown", () => {
  it("derives the four per-class counts from real DamageSummary aggregates", () => {
    const summary: DamageSummary = {
      total_buildings: 10,
      damaged_buildings: 7,
      severely_damaged: 4,
      destroyed: 2,
    };

    expect(deriveDamageBreakdown(summary)).toEqual({
      no_damage: 3,
      minor: 3,
      major: 2,
      destroyed: 2,
    });
  });

  it("never returns negative counts for well-formed but edge-case input", () => {
    const summary: DamageSummary = {
      total_buildings: 0,
      damaged_buildings: 0,
      severely_damaged: 0,
      destroyed: 0,
    };

    expect(deriveDamageBreakdown(summary)).toEqual({
      no_damage: 0,
      minor: 0,
      major: 0,
      destroyed: 0,
    });
  });
});

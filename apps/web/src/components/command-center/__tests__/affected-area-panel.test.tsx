import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DamageFeatureCollection } from "@sentinelai/shared";

import { AffectedAreaPanel } from "@/components/command-center/affected-area-panel";

const geographicCollection: DamageFeatureCollection = {
  type: "FeatureCollection",
  coordinate_reference_system: "EPSG:4326",
  features: [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [-1, -1] },
      properties: { building_id: "b1", damage_class: "major", confidence: 0.9, priority: "high", georeferenced: true },
    },
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [1, 1] },
      properties: { building_id: "b2", damage_class: "minor", confidence: 0.8, priority: "low", georeferenced: true },
    },
  ],
};

const imageSpaceCollection: DamageFeatureCollection = {
  ...geographicCollection,
  coordinate_reference_system: "IMAGE",
};

const baseProps = {
  isDamageLoading: false,
  isDamageError: false,
  isBriefingAvailable: false,
  priorityArea: null,
};

describe("AffectedAreaPanel", () => {
  it("shows an honest empty state, never a fabricated area, when damage data isn't available", () => {
    render(
      <AffectedAreaPanel
        {...baseProps}
        featureCollection={null}
        damageAvailable={false}
        damageReason="Analysis is not completed yet (status=processing)."
      />,
    );
    expect(screen.getByText(/status=processing/)).toBeInTheDocument();
    expect(screen.queryByText(/km²/)).not.toBeInTheDocument();
  });

  it("never treats image-pixel coordinates as a real-world area", () => {
    render(
      <AffectedAreaPanel
        {...baseProps}
        featureCollection={imageSpaceCollection}
        damageAvailable={true}
        damageReason={null}
      />,
    );
    expect(screen.queryByText(/km²/)).not.toBeInTheDocument();
    expect(screen.getByText(/image coordinates/i)).toBeInTheDocument();
  });

  it("computes a real bounding-box area from real WGS84 damage coordinates", () => {
    render(
      <AffectedAreaPanel
        {...baseProps}
        featureCollection={geographicCollection}
        damageAvailable={true}
        damageReason={null}
      />,
    );
    expect(screen.getByText(/km²/)).toBeInTheDocument();
  });

  it("shows the AI-generated priority area only once the briefing is available", () => {
    const { rerender } = render(
      <AffectedAreaPanel {...baseProps} featureCollection={null} damageAvailable={false} damageReason={null} />,
    );
    expect(screen.getByText(/will be generated once the analysis is complete/i)).toBeInTheDocument();

    rerender(
      <AffectedAreaPanel
        {...baseProps}
        featureCollection={null}
        damageAvailable={false}
        damageReason={null}
        isBriefingAvailable={true}
        priorityArea="3 high-priority structure(s) were identified."
      />,
    );
    expect(screen.getByText("3 high-priority structure(s) were identified.")).toBeInTheDocument();
  });
});

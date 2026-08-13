import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnalysisStateIndicator } from "@/components/command-center/analysis-state";

describe("AnalysisStateIndicator", () => {
  it("shows the exact copy the milestone specifies for uploading", () => {
    render(<AnalysisStateIndicator state="uploading" />);
    expect(screen.getByText("Uploading satellite imagery...")).toBeInTheDocument();
  });

  it("shows the exact copy the milestone specifies for processing", () => {
    render(<AnalysisStateIndicator state="processing" />);
    expect(screen.getByText("Analyzing disaster damage...")).toBeInTheDocument();
  });

  it("shows the exact copy the milestone specifies for completed", () => {
    render(<AnalysisStateIndicator state="completed" />);
    expect(screen.getByText("Incident assessment ready.")).toBeInTheDocument();
  });

  it("shows the backend's real failure message, not a generic string, when one is provided", () => {
    render(
      <AnalysisStateIndicator
        state="failed"
        failure={{ code: "MODEL_UNAVAILABLE", message: "The damage-detection model is not available." }}
      />,
    );
    expect(screen.getByText("The damage-detection model is not available.")).toBeInTheDocument();
  });

  it("exposes the state via role=status for assistive technology", () => {
    render(<AnalysisStateIndicator state="processing" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnalysisStageTracker } from "@/components/command-center/analysis-stage-tracker";

describe("AnalysisStageTracker", () => {
  it("renders exactly the three stages with a real backend signal — never Risk/Route/Briefing as false pipeline sub-stages", () => {
    render(<AnalysisStageTracker analysisState="processing" failure={null} />);

    expect(screen.getByText("Image received")).toBeInTheDocument();
    expect(screen.getByText("Preprocessing")).toBeInTheDocument();
    expect(screen.getByText("Damage analysis")).toBeInTheDocument();

    // These are independent, completed-gated resources — not sequential
    // sub-stages of this tracker. See the component's own doc comment and
    // `docs/architecture/frontend.md`, "Analysis stage tracking".
    expect(screen.queryByText("Risk assessment")).not.toBeInTheDocument();
    expect(screen.queryByText("Route optimization")).not.toBeInTheDocument();
    expect(screen.queryByText("Incident briefing")).not.toBeInTheDocument();
  });

  it("Preprocessing is always honestly 'Not yet available', regardless of analysis state", () => {
    render(<AnalysisStageTracker analysisState="completed" failure={null} />);
    expect(screen.getByText(/not yet available/i)).toBeInTheDocument();
  });

  it("reflects a real failure message on the Damage analysis row, not a generic string", () => {
    render(
      <AnalysisStageTracker
        analysisState="failed"
        failure={{ code: "MODEL_UNAVAILABLE", message: "Analysis could not be completed: no model." }}
      />,
    );
    expect(screen.getByText("Analysis could not be completed: no model.")).toBeInTheDocument();
  });

  it("Image received completes as soon as an id exists, before Damage analysis starts", () => {
    render(<AnalysisStageTracker analysisState="uploaded" failure={null} />);
    expect(screen.getByText("Image uploaded to the backend.")).toBeInTheDocument();
    expect(screen.getByText("Waiting to start.")).toBeInTheDocument();
  });
});

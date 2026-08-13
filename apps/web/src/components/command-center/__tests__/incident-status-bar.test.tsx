import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { IncidentStatusBar } from "@/components/command-center/incident-status-bar";

describe("IncidentStatusBar", () => {
  it("shows severity with a non-color text code, not color alone", () => {
    render(
      <IncidentStatusBar
        analysisState="completed"
        severity="critical"
        totalStructures={12}
        isDemoMode={false}
      />,
    );
    expect(screen.getByText(/CRITICAL/)).toBeInTheDocument();
  });

  it("shows a demo-mode badge only when demo mode is active", () => {
    const { rerender } = render(
      <IncidentStatusBar analysisState="idle" severity={null} totalStructures={null} isDemoMode={false} />,
    );
    expect(screen.queryByText("Demo mode")).not.toBeInTheDocument();

    rerender(
      <IncidentStatusBar analysisState="completed" severity="high" totalStructures={6} isDemoMode={true} />,
    );
    expect(screen.getByText("Demo mode")).toBeInTheDocument();
  });

  it("renders an em-dash rather than fabricating a severity when none is known yet", () => {
    render(
      <IncidentStatusBar analysisState="idle" severity={null} totalStructures={null} isDemoMode={false} />,
    );
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});

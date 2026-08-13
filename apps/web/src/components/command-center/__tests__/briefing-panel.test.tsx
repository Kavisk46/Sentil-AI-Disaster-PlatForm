import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { IncidentBriefing } from "@sentinelai/shared";

import { BriefingPanel } from "@/components/command-center/briefing-panel";

const briefing: IncidentBriefing = {
  analysis_id: "11111111-1111-1111-1111-111111111111",
  incident_severity: "high",
  affected_structures: {
    total: 10,
    damaged: 7,
    severely_damaged: 4,
    destroyed: 2,
    high_priority_count: 3,
  },
  priority_area: "3 high-priority structure(s) were identified.",
  route_summary: "Information unavailable.",
  key_findings: ["10 structure(s) assessed: 7 damaged, 2 destroyed."],
  limitations: ["Damage predictions may be inaccurate."],
  confidence: "moderate",
  generated_at: "2026-01-01T00:00:00Z",
  source: "fallback",
  prompt_version: "incident_summary_v1",
  disclaimer: "This briefing is AI-assisted decision support, not a verified emergency assessment.",
};

describe("BriefingPanel", () => {
  it("always labels the panel AI-generated, never implying human/authoritative authorship", () => {
    render(
      <BriefingPanel briefing={briefing} isLoading={false} isError={false} isAvailable={true} />,
    );
    expect(screen.getByText("AI-Generated Incident Briefing")).toBeInTheDocument();
  });

  it("shows severity and confidence as text badges (not color-only)", () => {
    render(
      <BriefingPanel briefing={briefing} isLoading={false} isError={false} isAvailable={true} />,
    );
    expect(screen.getByText(/Severity: High/i)).toBeInTheDocument();
    expect(screen.getByText(/Confidence: Moderate/i)).toBeInTheDocument();
  });

  it("always renders the backend's fixed safety disclaimer", () => {
    render(
      <BriefingPanel briefing={briefing} isLoading={false} isError={false} isAvailable={true} />,
    );
    expect(screen.getByText(briefing.disclaimer)).toBeInTheDocument();
  });

  it("shows a clear empty state before the analysis is complete", () => {
    render(<BriefingPanel briefing={null} isLoading={false} isError={false} isAvailable={false} />);
    expect(screen.getByText(/will be generated once the analysis is complete/i)).toBeInTheDocument();
  });

  it("shows an error state without exposing internals", () => {
    render(
      <BriefingPanel
        briefing={null}
        isLoading={false}
        isError={true}
        errorMessage="404 Not Found"
        isAvailable={true}
      />,
    );
    expect(screen.getByText("Briefing unavailable")).toBeInTheDocument();
    expect(screen.getByText("404 Not Found")).toBeInTheDocument();
  });
});

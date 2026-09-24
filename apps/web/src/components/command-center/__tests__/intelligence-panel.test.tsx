import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AnalysisCapabilityMatch, Recommendation, SearchZone } from "@sentinelai/shared";

import { IntelligencePanel } from "@/components/command-center/intelligence-panel";

const criticalZone: SearchZone = {
  id: "zone-critical",
  geometry: { type: "point", coordinates: [1.499, 1.499] },
  geometry_crs: "EPSG:4326",
  priority_score: 0.91,
  priority_level: "critical",
  factors: [
    {
      name: "damage_severity",
      value: 1.0,
      weight: 0.5,
      contribution: 0.5,
      description: "Destroyed structures observed.",
    },
  ],
  missing_factors: ["population_exposure"],
  reasons: ["Destroyed structures observed.", "Population exposure could not be scored."],
  supporting_observations: [],
  supporting_evidence: [
    {
      id: "evidence-1",
      source_type: "damage_analysis",
      observation_id: null,
      source: "analysis",
      originating_subsystem: "app.intelligence.analysis_adapter",
      timestamp: "2026-01-01T00:00:00Z",
      summary: "Building-damage classification: destroyed.",
      data_ref: "building-1",
    },
  ],
  uncertainty: {
    level: "moderate",
    confidence: null,
    reason: "Some factors were unavailable.",
    missing_information: ["population_exposure"],
    source_limitations: [],
  },
  is_simulated: false,
};

const moderateZone: SearchZone = {
  ...criticalZone,
  id: "zone-moderate",
  priority_score: 0.4,
  priority_level: "moderate",
  reasons: ["Major damage observed."],
};

const eligibleCandidate: AnalysisCapabilityMatch = {
  match: {
    resource_id: "resource-ground-team",
    can_perform_task: true,
    missing_capabilities: [],
    is_available: true,
    distance_meters: 210,
    reachability: "reachable",
    route_operational: true,
    eligible: true,
    match_score: 0.9,
    rationale: ["Capability match: yes.", "Availability: available."],
    is_simulated: true,
  },
  route: {
    routing_mode: "risk_aware",
    found: true,
    start_node: "A",
    destination_node: "B",
    node_sequence: ["A", "B"],
    edge_sequence: [],
    route_geometry: [
      [1.4985, 1.4988],
      [1.499, 1.499],
    ],
    total_distance: 210,
    total_cost: 210,
    accumulated_risk: 0.1,
    number_of_edges: 1,
    accessibility_summary: { open: 1, restricted: 0, blocked: 0, unknown: 0 },
    reason: null,
  },
  route_feasibility: { status: "computed", reason: null },
};

const ineligibleCandidate: AnalysisCapabilityMatch = {
  match: {
    resource_id: "resource-ambulance",
    can_perform_task: false,
    missing_capabilities: ["ground_search"],
    is_available: true,
    distance_meters: null,
    reachability: "unknown",
    route_operational: null,
    eligible: false,
    match_score: 0.45,
    rationale: ["Capability match: no (missing: ground_search)."],
    is_simulated: true,
  },
  route: null,
  route_feasibility: {
    status: "not_applicable",
    reason: "Candidate did not pass an earlier capability/availability/reachability gate.",
  },
};

const recommendation: Recommendation = {
  id: "rec-1",
  action: "deploy_ground_search_team",
  target_id: "zone-critical",
  target_description: "Critical-priority search zone.",
  priority: "critical",
  rationale: "An eligible, available, reachable ground search team was matched.",
  required_capabilities: ["ground_search"],
  supporting_evidence: [
    {
      id: "evidence-rec-1",
      source_type: "resource_registry",
      observation_id: null,
      source: "analysis",
      originating_subsystem: "app.intelligence.recommendation",
      timestamp: "2026-01-01T00:00:00Z",
      summary: "Top-ranked capability match: resource-ground-team.",
      data_ref: "resource-ground-team",
    },
  ],
  uncertainty: {
    level: "low",
    confidence: null,
    reason: "Directly derived from a computed capability match.",
    missing_information: [],
    source_limitations: [],
  },
  limitations: ["No ground-truth confirmation."],
  is_simulated: false,
};

function baseProps() {
  return {
    contextAvailable: true,
    contextUnavailableReason: null,
    isSimulated: false,
    searchZones: [criticalZone, moderateZone],
    isSearchZonesLoading: false,
    isSearchZonesError: false,
    recommendations: [recommendation],
    isRecommendationsLoading: false,
    isRecommendationsError: false,
    topSearchZoneId: criticalZone.id,
    resourceView: { kind: "candidates" as const, candidates: [eligibleCandidate, ineligibleCandidate] },
    resourcesAreDemo: true,
    roadsAvailable: true,
    roadsUnavailableReason: null,
  };
}

describe("IntelligencePanel", () => {
  it("shows a loading state", () => {
    const { container } = render(
      <IntelligencePanel {...baseProps()} isSearchZonesLoading={true} />,
    );
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0);
  });

  it("shows an error state with the real backend message, not fabricated content", () => {
    render(
      <IntelligencePanel
        {...baseProps()}
        isSearchZonesError={true}
        searchZonesErrorMessage="503 Service Unavailable"
      />,
    );
    expect(screen.getByText("Intelligence data unavailable")).toBeInTheDocument();
    expect(screen.getByText("503 Service Unavailable")).toBeInTheDocument();
  });

  it("shows the explicit unavailable reason instead of an empty or fabricated view", () => {
    render(
      <IntelligencePanel
        {...baseProps()}
        contextAvailable={false}
        contextUnavailableReason="NO_GEOREFERENCE"
        searchZones={[]}
        recommendations={[]}
      />,
    );
    // The reason also appears a second time in the always-rendered
    // Limitations section below — assert on at least one occurrence
    // rather than a single unique match.
    expect(screen.getAllByText(/NO_GEOREFERENCE/).length).toBeGreaterThan(0);
  });

  it("renders every search zone, ranked, with priority badges and never a location claim", () => {
    render(<IntelligencePanel {...baseProps()} />);
    expect(screen.getByText("Where should we act first?")).toBeInTheDocument();
    expect(screen.getByText(/CRITICAL \(0\.91\)/)).toBeInTheDocument();
    expect(screen.getByText(/MODERATE \(0\.40\)/)).toBeInTheDocument();
    expect(screen.getByText("Top priority")).toBeInTheDocument();
    expect(screen.queryByText(/located here/i)).not.toBeInTheDocument();
  });

  it("shows the selected (top) zone's reasons, evidence, and uncertainty in the Why section", () => {
    render(<IntelligencePanel {...baseProps()} />);
    expect(screen.getByText("Why")).toBeInTheDocument();
    expect(screen.getByText("Destroyed structures observed.")).toBeInTheDocument();
    expect(screen.getByText(/Building-damage classification: destroyed\./)).toBeInTheDocument();
    expect(screen.getByText(/Some factors were unavailable\./)).toBeInTheDocument();
  });

  it("never renders a fabricated numeric confidence when uncertainty.confidence is null", () => {
    render(<IntelligencePanel {...baseProps()} />);
    // The zone's uncertainty has confidence: null — its certainty badge
    // must show the qualitative level only, no "(NN%)" suffix.
    const whySection = screen.getByText("Why").closest("section")!;
    expect(within(whySection).queryByText(/%\)/)).not.toBeInTheDocument();
  });

  it("renders resource candidates with eligible/ineligible states and route feasibility", () => {
    render(<IntelligencePanel {...baseProps()} />);
    expect(screen.getByText("What can reach it?")).toBeInTheDocument();
    expect(screen.getByText("Eligible")).toBeInTheDocument();
    expect(screen.getByText("Not eligible")).toBeInTheDocument();
    expect(screen.getByText(/Computed — 210 m/)).toBeInTheDocument();
    expect(
      screen.getByText(
        "Candidate did not pass an earlier capability/availability/reachability gate.",
      ),
    ).toBeInTheDocument();
  });

  it("marks resource candidates as simulated even when the surrounding analysis is real", () => {
    render(<IntelligencePanel {...baseProps()} isSimulated={false} />);
    // isSimulated=false means the panel-level badge reads "CALC", but
    // every resource candidate row still carries its own "SIM" badge —
    // resources_are_demo is an independent signal (see intelligence-panel.tsx).
    expect(screen.getAllByText("CALC").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SIM").length).toBeGreaterThan(0);
  });

  it("labels the whole panel as simulated in Demo mode", () => {
    render(<IntelligencePanel {...baseProps()} isSimulated={true} />);
    const header = screen.getByText("Search & response intelligence").closest("div")!;
    expect(within(header).getByText("SIM")).toBeInTheDocument();
  });

  it("renders recommendation rationale, required capabilities, and limitations", () => {
    render(<IntelligencePanel {...baseProps()} />);
    expect(screen.getByText("Recommended action")).toBeInTheDocument();
    expect(screen.getByText("Deploy ground search team")).toBeInTheDocument();
    expect(
      screen.getByText("An eligible, available, reachable ground search team was matched."),
    ).toBeInTheDocument();
    // Exact text, not a loose /ground_search/ regex — that substring also
    // appears in the (unrelated) ineligible candidate's own rationale and
    // missing-capabilities text below, which would make the query ambiguous.
    expect(screen.getByText("Requires: ground_search")).toBeInTheDocument();
    expect(screen.getByText("No ground-truth confirmation.")).toBeInTheDocument();
  });

  it("always discloses simulated resources and the no-ground-truth caveat in Limitations", () => {
    render(<IntelligencePanel {...baseProps()} />);
    const limitations = screen.getByText("Limitations").closest("section")!;
    expect(within(limitations).getByText(/deterministic demo pool/)).toBeInTheDocument();
    expect(
      within(limitations).getByText(/No ground-truth confirmation — every search zone/),
    ).toBeInTheDocument();
  });

  it("F6.1: falls back to internal state when selectedZoneId/onSelectZone are not provided (uncontrolled)", () => {
    render(<IntelligencePanel {...baseProps()} />);
    // The critical zone is the top zone and starts selected; clicking the
    // moderate zone's button must switch the "Why" section to it without
    // any controlling parent — internal `useState` still works exactly as
    // before this milestone.
    fireEvent.click(screen.getByText(/MODERATE \(0\.40\)/).closest("button")!);
    expect(screen.getByText("Major damage observed.")).toBeInTheDocument();
  });

  it("F6.1: is controlled when selectedZoneId/onSelectZone are provided, so the map and panel can stay in sync", () => {
    const onSelectZone = vi.fn();
    const { rerender } = render(
      <IntelligencePanel {...baseProps()} selectedZoneId={criticalZone.id} onSelectZone={onSelectZone} />,
    );

    // Clicking a zone calls the callback (e.g. to update `command-center.tsx`'s
    // lifted state) rather than switching an internal state the caller
    // can't see.
    fireEvent.click(screen.getByText(/MODERATE \(0\.40\)/).closest("button")!);
    expect(onSelectZone).toHaveBeenCalledWith(moderateZone.id);
    // Since selection is controlled, the panel does NOT switch on its own —
    // the "Why" section still reflects the `selectedZoneId` prop, which the
    // parent hasn't changed yet in this test.
    expect(screen.getByText("Destroyed structures observed.")).toBeInTheDocument();

    // The parent applying the callback's result re-renders with the new
    // controlled value, and the panel follows it.
    rerender(
      <IntelligencePanel {...baseProps()} selectedZoneId={moderateZone.id} onSelectZone={onSelectZone} />,
    );
    expect(screen.getByText("Major damage observed.")).toBeInTheDocument();
  });

  it("surfaces roads-unavailable as a limitation when route feasibility could not be assessed", () => {
    render(
      <IntelligencePanel
        {...baseProps()}
        roadsAvailable={false}
        roadsUnavailableReason="No road network is loaded for this analysis."
      />,
    );
    const limitations = screen.getByText("Limitations").closest("section")!;
    expect(
      within(limitations).getByText("No road network is loaded for this analysis."),
    ).toBeInTheDocument();
  });
});

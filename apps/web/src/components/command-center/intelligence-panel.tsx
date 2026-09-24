import * as React from "react";

import type {
  AnalysisCapabilityMatch,
  Recommendation,
  RecommendationAction,
  SearchZone,
} from "@sentinelai/shared";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProvenanceBadge } from "@/components/ui/provenance-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { SEARCH_PRIORITY_STYLE } from "@/lib/risk-colors";
import { cn } from "@/lib/utils";

const ACTION_LABEL: Record<RecommendationAction, string> = {
  deploy_drone_recon: "Deploy drone reconnaissance",
  deploy_ground_search_team: "Deploy ground search team",
  deploy_medical_team: "Deploy medical team",
  inspect_infrastructure_before_dispatch: "Inspect infrastructure before dispatch",
  avoid_route_due_to_hazard: "Avoid route due to hazard",
  escalate_for_additional_resources: "Escalate for additional resources",
  hold_pending_more_information: "Hold pending more information",
};

/**
 * What to render for "What can reach it?" — the top-priority zone's
 * resource-capability-match candidates (real F3 data in Analysis mode,
 * hand-authored `DEMO_RESOURCE_CANDIDATES` in Demo mode — see
 * `lib/demo/demo-data.ts`), or nothing when neither exists yet.
 */
export type ResourceView =
  | { kind: "candidates"; candidates: AnalysisCapabilityMatch[] }
  | { kind: "unavailable" };

export interface IntelligencePanelProps {
  contextAvailable: boolean;
  contextUnavailableReason: string | null;
  /** True for the F2 demo scenario, false for real F3 analysis-derived
   * search zones/recommendations — independent of `resourcesAreDemo`
   * below, which can be true even when this is false. */
  isSimulated: boolean;
  searchZones: SearchZone[];
  isSearchZonesLoading: boolean;
  isSearchZonesError: boolean;
  searchZonesErrorMessage?: string;
  recommendations: Recommendation[];
  isRecommendationsLoading: boolean;
  isRecommendationsError: boolean;
  recommendationsErrorMessage?: string;
  topSearchZoneId: string | null;
  resourceView: ResourceView;
  /** Always true today — no real resource-ingestion system exists yet
   * (see `app.intelligence.analysis_adapter`) — carried explicitly so
   * this panel never has to guess. */
  resourcesAreDemo: boolean;
  roadsAvailable: boolean;
  roadsUnavailableReason: string | null;
  /**
   * F6.1: optional controlled selection, so the map (`command-map.tsx`)
   * and this panel can stay in sync — clicking a zone on the map
   * highlights it here, and vice versa. Both omitted (the panel's
   * original behavior, and every existing test's) falls back to this
   * component's own internal `useState`, so nothing controlled-mode-only
   * breaks a caller that doesn't need synchronization (e.g. a future
   * standalone usage, or a test rendering this panel in isolation).
   */
  selectedZoneId?: string | null;
  onSelectZone?: (zoneId: string) => void;
  className?: string;
}

function UncertaintyBlock({ uncertainty }: { uncertainty: SearchZone["uncertainty"] }) {
  return (
    <div className="flex flex-col gap-1 text-xs">
      <div className="flex items-center gap-1.5">
        <span className="text-muted-foreground font-medium tracking-wide uppercase">
          Certainty:
        </span>
        <Badge variant="outline" className="text-[10px]">
          {uncertainty.level === "unknown" ? "Unavailable" : uncertainty.level.toUpperCase()}
        </Badge>
        {/* Never a fabricated numeric confidence — only rendered when the
            backend genuinely provides one (it does not, in this milestone). */}
        {uncertainty.confidence !== null && (
          <span className="text-muted-foreground">
            ({Math.round(uncertainty.confidence * 100)}%)
          </span>
        )}
      </div>
      <p className="text-muted-foreground">{uncertainty.reason}</p>
      {uncertainty.missing_information.length > 0 && (
        <p className="text-muted-foreground">
          Missing: {uncertainty.missing_information.join(", ")}
        </p>
      )}
    </div>
  );
}

function ZoneWhy({ zone }: { zone: SearchZone }) {
  const style = SEARCH_PRIORITY_STYLE[zone.priority_level];
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border/60 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium">
          Why this zone is{" "}
          <span className={cn("rounded px-1 py-0.5 text-xs", style.className)}>
            {style.label.toUpperCase()}
          </span>
        </p>
        <ProvenanceBadge category="calculated" />
      </div>

      {/* Never "a person is located here" — always framed as evidence
          supporting a search-priority assessment. See
          app/intelligence/schemas.py's SearchZone doc comment. */}
      <ul className="flex list-disc flex-col gap-1 pl-4 text-xs">
        {zone.reasons.map((reason, index) => (
          <li key={index}>{reason}</li>
        ))}
      </ul>

      {zone.missing_factors.length > 0 && (
        <p className="text-muted-foreground text-xs">
          Not scored (data unavailable): {zone.missing_factors.join(", ")}
        </p>
      )}

      {zone.supporting_evidence.length > 0 && (
        <div className="flex flex-col gap-1">
          <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            Evidence
          </p>
          <ul className="flex flex-col gap-1 text-xs">
            {zone.supporting_evidence.map((evidence) => (
              <li key={evidence.id} className="text-muted-foreground">
                {evidence.summary}{" "}
                <span className="text-[10px] uppercase">({evidence.source_type})</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <UncertaintyBlock uncertainty={zone.uncertainty} />
    </div>
  );
}

function ResourceCandidateRow({ entry }: { entry: AnalysisCapabilityMatch }) {
  const { match, route, route_feasibility } = entry;
  return (
    <li className="flex flex-col gap-1.5 rounded-md border border-border/60 p-2.5 text-xs">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant={match.eligible ? "default" : "outline"} className="text-[10px]">
          {match.eligible ? "Eligible" : "Not eligible"}
        </Badge>
        <Badge variant="outline" className="text-[10px]">
          {match.can_perform_task ? "Can perform task" : "Missing capability"}
        </Badge>
        <Badge variant="outline" className="text-[10px]">
          {match.is_available ? "Available" : "Unavailable"}
        </Badge>
        <Badge variant="outline" className="text-[10px]">
          Reach: {match.reachability === "unknown" ? "Unavailable" : match.reachability}
        </Badge>
        <ProvenanceBadge category="simulated" />
      </div>

      {match.missing_capabilities.length > 0 && (
        <p className="text-muted-foreground">
          Missing capabilities: {match.missing_capabilities.join(", ")}
        </p>
      )}

      <ul className="text-muted-foreground list-disc pl-4">
        {match.rationale.map((line, index) => (
          <li key={index}>{line}</li>
        ))}
      </ul>

      <p>
        <span className="font-medium">Route:</span>{" "}
        {route_feasibility.status === "computed" && route?.found && (
          <span>
            Computed — {route.total_distance !== null ? `${Math.round(route.total_distance)} m` : "distance unknown"}
            {route.accumulated_risk !== null ? `, risk score ${route.accumulated_risk.toFixed(2)}` : ""}
          </span>
        )}
        {route_feasibility.status === "computed" && route && !route.found && (
          <span className="text-muted-foreground">
            No path found on the loaded road network ({route.reason ?? "unknown reason"}).
          </span>
        )}
        {route_feasibility.status === "route_unavailable" && (
          <span className="text-muted-foreground">
            Route unavailable — {route_feasibility.reason ?? "no road network is loaded."}
          </span>
        )}
        {route_feasibility.status === "not_applicable" && (
          <span className="text-muted-foreground">
            {route_feasibility.reason ?? "Not computed for this candidate."}
          </span>
        )}
      </p>
    </li>
  );
}

function RecommendationRow({ recommendation }: { recommendation: Recommendation }) {
  const priorityStyle = SEARCH_PRIORITY_STYLE[recommendation.priority];
  return (
    <li className="flex flex-col gap-2 rounded-md border border-border/60 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">{ACTION_LABEL[recommendation.action]}</p>
        <div className="flex items-center gap-1.5">
          <Badge variant="outline" className={priorityStyle.className}>
            {priorityStyle.code} {priorityStyle.label.toUpperCase()}
          </Badge>
          {recommendation.is_simulated && <ProvenanceBadge category="simulated" />}
        </div>
      </div>

      <p className="text-muted-foreground text-xs">{recommendation.target_description}</p>
      <p className="text-sm">{recommendation.rationale}</p>

      {recommendation.required_capabilities.length > 0 && (
        <p className="text-muted-foreground text-xs">
          Requires: {recommendation.required_capabilities.join(", ")}
        </p>
      )}

      <UncertaintyBlock uncertainty={recommendation.uncertainty} />

      {recommendation.limitations.length > 0 && (
        <ul className="text-muted-foreground list-disc pl-4 text-xs">
          {recommendation.limitations.map((limitation, index) => (
            <li key={index}>{limitation}</li>
          ))}
        </ul>
      )}
    </li>
  );
}

/**
 * "Where should we act first? / Why? / What can reach it? / Recommended
 * action / Limitations" — the F3 search-and-response section, added to
 * the existing results grid rather than a redesigned dashboard (see
 * `results-panel-grid.tsx`). Sourced from either F2's demo scenario (Demo
 * mode) or F3's real analysis-derived intelligence — `command-center.tsx`
 * normalizes both into these same props so this component never branches
 * on which mode produced them, only on what's actually available.
 */
export function IntelligencePanel({
  contextAvailable,
  contextUnavailableReason,
  isSimulated,
  searchZones,
  isSearchZonesLoading,
  isSearchZonesError,
  searchZonesErrorMessage,
  recommendations,
  isRecommendationsLoading,
  isRecommendationsError,
  recommendationsErrorMessage,
  topSearchZoneId,
  resourceView,
  resourcesAreDemo,
  roadsAvailable,
  roadsUnavailableReason,
  selectedZoneId: controlledSelectedZoneId,
  onSelectZone,
  className,
}: IntelligencePanelProps) {
  const [internalSelectedZoneId, setInternalSelectedZoneId] = React.useState<string | null>(null);
  // Controlled when the caller passes `selectedZoneId`/`onSelectZone`
  // (`command-center.tsx`, so the map stays in sync); uncontrolled
  // otherwise — see the prop's own doc comment.
  const isControlled = controlledSelectedZoneId !== undefined;
  const selectedZoneId = isControlled ? controlledSelectedZoneId : internalSelectedZoneId;
  const setSelectedZoneId = isControlled ? (onSelectZone ?? (() => {})) : setInternalSelectedZoneId;
  const effectiveSelectedZoneId = selectedZoneId ?? topSearchZoneId ?? searchZones[0]?.id ?? null;
  const selectedZone = searchZones.find((zone) => zone.id === effectiveSelectedZoneId) ?? null;

  const isLoading = isSearchZonesLoading || isRecommendationsLoading;
  const isError = isSearchZonesError || isRecommendationsError;

  const limitations: string[] = [];
  if (contextUnavailableReason) limitations.push(`Intelligence context: ${contextUnavailableReason}`);
  if (!roadsAvailable) {
    limitations.push(roadsUnavailableReason ?? "Road network unavailable — route feasibility cannot be assessed.");
  }
  if (resourcesAreDemo) {
    limitations.push(
      "No real resource-ingestion system exists yet — resource candidates are a deterministic demo pool, not live telemetry.",
    );
  }
  limitations.push("No ground-truth confirmation — every search zone is a priority estimate, not a location claim.");

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle>Search &amp; response intelligence</CardTitle>
          <ProvenanceBadge category={isSimulated ? "simulated" : "calculated"} />
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {isLoading && (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        )}

        {!isLoading && isError && (
          <Alert variant="destructive">
            <AlertTitle>Intelligence data unavailable</AlertTitle>
            <AlertDescription>
              {searchZonesErrorMessage ?? recommendationsErrorMessage ?? "The backend could not be reached."}
            </AlertDescription>
          </Alert>
        )}

        {!isLoading && !isError && !contextAvailable && (
          <p className="text-muted-foreground text-sm">
            {contextUnavailableReason
              ? `Not enough analysis data to build intelligence yet (${contextUnavailableReason}).`
              : "Not enough analysis data to build intelligence yet."}
          </p>
        )}

        {!isLoading && !isError && contextAvailable && (
          <>
            <section className="flex flex-col gap-2">
              <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                Where should we act first?
              </p>
              {searchZones.length === 0 ? (
                <p className="text-muted-foreground text-sm">No search zones were scored.</p>
              ) : (
                <ul className="flex flex-col gap-1.5">
                  {searchZones.map((zone, index) => {
                    const style = SEARCH_PRIORITY_STYLE[zone.priority_level];
                    const isSelected = zone.id === effectiveSelectedZoneId;
                    return (
                      <li key={zone.id}>
                        <Button
                          type="button"
                          variant={isSelected ? "secondary" : "outline"}
                          size="sm"
                          aria-pressed={isSelected}
                          className="h-auto w-full justify-between py-1.5"
                          onClick={() => setSelectedZoneId(zone.id)}
                        >
                          <span className="flex items-center gap-2">
                            <span className="text-muted-foreground">#{index + 1}</span>
                            {zone.id === topSearchZoneId && (
                              <span className="text-muted-foreground text-[10px] uppercase">
                                Top priority
                              </span>
                            )}
                          </span>
                          <Badge variant="outline" className={style.className}>
                            {style.code} {style.label.toUpperCase()} ({zone.priority_score.toFixed(2)})
                          </Badge>
                        </Button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>

            {selectedZone && (
              <section className="flex flex-col gap-2">
                <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">Why</p>
                <ZoneWhy zone={selectedZone} />
              </section>
            )}

            <section className="flex flex-col gap-2">
              <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                What can reach it?
              </p>
              {effectiveSelectedZoneId !== null && effectiveSelectedZoneId !== topSearchZoneId && (
                <p className="text-muted-foreground text-xs">
                  Resource matching is only computed for the top-priority zone shown above.
                </p>
              )}
              {resourceView.kind === "unavailable" && (
                <p className="text-muted-foreground text-sm">No resource data is available.</p>
              )}
              {resourceView.kind === "candidates" &&
                (resourceView.candidates.length === 0 ? (
                  <p className="text-muted-foreground text-sm">No resource candidates were matched.</p>
                ) : (
                  <ul className="flex flex-col gap-1.5">
                    {resourceView.candidates.map((entry) => (
                      <ResourceCandidateRow key={entry.match.resource_id} entry={entry} />
                    ))}
                  </ul>
                ))}
            </section>

            <section className="flex flex-col gap-2">
              <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                Recommended action
              </p>
              {recommendations.length === 0 ? (
                <p className="text-muted-foreground text-sm">No recommendations yet.</p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {recommendations.map((recommendation) => (
                    <RecommendationRow key={recommendation.id} recommendation={recommendation} />
                  ))}
                </ul>
              )}
            </section>
          </>
        )}

        <section className="flex flex-col gap-1.5 border-t border-border/60 pt-3">
          <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            Limitations
          </p>
          <ul className="text-muted-foreground list-disc pl-4 text-xs">
            {limitations.map((limitation, index) => (
              <li key={index}>{limitation}</li>
            ))}
          </ul>
        </section>
      </CardContent>
    </Card>
  );
}

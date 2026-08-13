"use client";

import * as React from "react";
import { MapPinOff } from "lucide-react";

import { BriefingPanel } from "@/components/command-center/briefing-panel";
import { DamageStatsPanel } from "@/components/command-center/damage-stats-panel";
import { IncidentStatusBar } from "@/components/command-center/incident-status-bar";
import type { ClientAnalysisState } from "@/components/command-center/analysis-state";
import { RoadRiskPanel } from "@/components/command-center/road-risk-panel";
import { RouteComparisonPanel } from "@/components/command-center/route-comparison-panel";
import { UploadPanel } from "@/components/command-center/upload-panel";
import { CommandMapLoader } from "@/components/map/command-map-loader";
import { MapLegend } from "@/components/map/map-legend";
import { Button } from "@/components/ui/button";
import { useAnalysis, useDamageMap, useUploadAnalysis } from "@/hooks/use-analysis";
import { useIncidentSummary, useRegenerateIncidentSummary } from "@/hooks/use-incident-summary";
import { useRoadRisk } from "@/hooks/use-road-risk";
import { useRouteComparison } from "@/hooks/use-routing";
import {
  DEMO_DAMAGE_MAP,
  DEMO_DAMAGE_SUMMARY,
  DEMO_INCIDENT_BRIEFING,
  DEMO_ROAD_RISK,
  DEMO_ROUTE_COMPARISON,
  DEMO_ROUTES,
} from "@/lib/demo/demo-data";
import { useIncidentStore } from "@/store/incident-store";
import { useUiStore } from "@/store/ui-store";

/**
 * The single owner of every data-fetching hook and every piece of derived
 * "which state is the app in" logic — every panel below it is presentational,
 * driven entirely by props. This is the "orchestrator" layer described in
 * `docs/architecture/frontend.md`: API -> hooks -> typed data -> this
 * component -> panels/map.
 */
export function CommandCenter() {
  const activeAnalysisId = useIncidentStore((state) => state.activeAnalysisId);
  const setActiveAnalysisId = useIncidentStore((state) => state.setActiveAnalysisId);
  const isDemoMode = useIncidentStore((state) => state.isDemoMode);
  const routeStart = useIncidentStore((state) => state.routeStart);
  const routeDestination = useIncidentStore((state) => state.routeDestination);
  const setRoutePoint = useIncidentStore((state) => state.setRoutePoint);
  const clearRoutePoints = useIncidentStore((state) => state.clearRoutePoints);
  const isPanelsOpen = useUiStore((state) => state.isSidebarOpen);
  const togglePanels = useUiStore((state) => state.toggleSidebar);

  const upload = useUploadAnalysis();
  const analysis = useAnalysis(isDemoMode ? null : activeAnalysisId);
  const isCompleted = !isDemoMode && analysis.data?.status === "completed";

  const damageMap = useDamageMap(activeAnalysisId, isCompleted);
  const roadRisk = useRoadRisk(activeAnalysisId, isCompleted);
  const summary = useIncidentSummary(activeAnalysisId, isCompleted);
  const regenerate = useRegenerateIncidentSummary(activeAnalysisId);
  const routeComparison = useRouteComparison(
    isDemoMode ? null : activeAnalysisId,
    routeStart,
    routeDestination,
  );

  const analysisState: ClientAnalysisState = isDemoMode
    ? "completed"
    : upload.isPending
      ? "uploading"
      : (analysis.data?.status ?? (activeAnalysisId ? "uploaded" : "idle"));

  const damage = isDemoMode ? DEMO_DAMAGE_MAP : damageMap.data;
  const roadRiskData = isDemoMode ? DEMO_ROAD_RISK : roadRisk.data;
  const briefing = isDemoMode ? DEMO_INCIDENT_BRIEFING : summary.data;
  const distanceOnlyRoute = isDemoMode
    ? DEMO_ROUTES.distanceOnly
    : (routeComparison.data?.distanceOnly ?? null);
  const riskAwareRoute = isDemoMode
    ? DEMO_ROUTES.riskAware
    : (routeComparison.data?.riskAware ?? null);
  const effectiveRouteStart = isDemoMode ? null : routeStart;
  const effectiveRouteDestination = isDemoMode ? null : routeDestination;

  // `DamageSummary` comes from `GET /api/v1/analysis/{id}` directly (not
  // the damage-map endpoint), so its availability/reason are derived from
  // the analysis's own lifecycle status, independent of whether spatial
  // (GeoJSON) data exists for the map.
  const damageSummary = isDemoMode ? DEMO_DAMAGE_SUMMARY : (analysis.data?.summary ?? null);
  const damageSummaryAvailable = isDemoMode || damageSummary !== null;
  const damageSummaryReason =
    !isDemoMode && !damageSummaryAvailable && analysis.data
      ? `Analysis is not completed yet (status=${analysis.data.status}).`
      : null;
  const totalStructures = damageSummary?.total_buildings ?? null;

  return (
    <div className="flex flex-1 flex-col gap-4 p-4">
      <IncidentStatusBar
        analysisState={analysisState}
        severity={briefing?.incident_severity ?? null}
        totalStructures={totalStructures}
        isDemoMode={isDemoMode}
      />

      <div className="grid flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="relative min-h-[420px] overflow-hidden rounded-xl border border-white/10 lg:min-h-0">
          <CommandMapLoader
            damage={damage?.available ? damage.feature_collection : null}
            distanceOnlyRoute={distanceOnlyRoute}
            riskAwareRoute={riskAwareRoute}
            routeStart={effectiveRouteStart}
            routeDestination={effectiveRouteDestination}
            onMapClick={
              isDemoMode
                ? undefined
                : (point) => setRoutePoint(routeStart === null ? "start" : "destination", point)
            }
            className="absolute inset-0"
          />
          <MapLegend />
          {!isDemoMode && (routeStart || routeDestination) && (
            <div className="absolute top-3 right-3 z-10">
              <Button
                size="sm"
                variant="secondary"
                className="bg-background/70 backdrop-blur-md"
                onClick={clearRoutePoints}
              >
                <MapPinOff className="size-3.5" />
                Clear points
              </Button>
            </div>
          )}
          <Button
            size="sm"
            variant="secondary"
            className="absolute bottom-3 right-3 z-10 bg-background/70 backdrop-blur-md lg:hidden"
            onClick={togglePanels}
            aria-expanded={isPanelsOpen}
            aria-controls="command-center-panels"
          >
            {isPanelsOpen ? "Hide panels" : "Show panels"}
          </Button>
        </div>

        <div
          id="command-center-panels"
          className={`${isPanelsOpen ? "flex" : "hidden"} flex-col gap-4 lg:flex lg:max-h-[calc(100vh-9rem)] lg:overflow-y-auto lg:pr-1`}
        >
          <UploadPanel
            isDemoMode={isDemoMode}
            hasActiveAnalysis={activeAnalysisId !== null}
            state={analysisState}
            failure={analysis.data?.failure ?? null}
            uploadErrorMessage={upload.isError ? upload.error.message : null}
            onFileSelected={(file) =>
              upload.mutate(file, {
                onSuccess: (result) => {
                  if (result.ok) setActiveAnalysisId(result.data.analysis_id);
                },
              })
            }
            onReset={() => {
              setActiveAnalysisId(null);
              upload.reset();
            }}
          />

          <RouteComparisonPanel
            comparison={isDemoMode ? DEMO_ROUTE_COMPARISON : (routeComparison.data ?? null)}
            hasSelectedPoints={isDemoMode || (routeStart !== null && routeDestination !== null)}
            isLoading={!isDemoMode && routeComparison.isLoading}
            isError={!isDemoMode && routeComparison.isError}
            errorMessage={!isDemoMode ? routeComparison.error?.message : undefined}
          />

          <BriefingPanel
            briefing={briefing ?? null}
            isLoading={!isDemoMode && summary.isLoading && isCompleted}
            isError={!isDemoMode && summary.isError}
            errorMessage={!isDemoMode ? summary.error?.message : undefined}
            isAvailable={isDemoMode || isCompleted}
            onRegenerate={
              isDemoMode
                ? undefined
                : () =>
                    regenerate.mutate(
                      routeStart && routeDestination
                        ? { start: routeStart, destination: routeDestination }
                        : undefined,
                    )
            }
            isRegenerating={regenerate.isPending}
          />

          <DamageStatsPanel
            summary={damageSummary}
            available={damageSummaryAvailable}
            reason={damageSummaryReason}
            highPriorityCount={briefing?.affected_structures.high_priority_count ?? null}
            isLoading={!isDemoMode && analysis.isLoading}
            isError={!isDemoMode && analysis.isError}
            errorMessage={!isDemoMode ? analysis.error?.message : undefined}
          />

          <RoadRiskPanel
            edges={roadRiskData?.edges ?? []}
            available={roadRiskData?.available ?? false}
            reason={roadRiskData?.reason ?? null}
            isLoading={!isDemoMode && roadRisk.isLoading && isCompleted}
            isError={!isDemoMode && roadRisk.isError}
            errorMessage={!isDemoMode ? roadRisk.error?.message : undefined}
          />
        </div>
      </div>
    </div>
  );
}

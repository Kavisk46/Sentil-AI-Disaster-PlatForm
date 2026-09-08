"use client";

import * as React from "react";
import { MapPinOff } from "lucide-react";

import { AnalysisWorkspace } from "@/components/command-center/analysis-workspace";
import { IncidentStatusBar } from "@/components/command-center/incident-status-bar";
import type { ClientAnalysisState } from "@/components/command-center/analysis-state";
import { ResultsPanelGrid } from "@/components/command-center/results-panel-grid";
import { CommandMapLoader } from "@/components/map/command-map-loader";
import { MapLegend } from "@/components/map/map-legend";
import { Button } from "@/components/ui/button";
import { useAnalysis, useDamageMap, useUploadAnalysis } from "@/hooks/use-analysis";
import {
  useAnalysisIntelligenceContext,
  useAnalysisRecommendations,
  useAnalysisSearchZones,
} from "@/hooks/use-analysis-intelligence";
import { useIncidentSummary, useRegenerateIncidentSummary } from "@/hooks/use-incident-summary";
import { useRoadRisk } from "@/hooks/use-road-risk";
import { useRouteComparison } from "@/hooks/use-routing";
import type { ResourceView } from "@/components/command-center/intelligence-panel";
import {
  DEMO_DAMAGE_MAP,
  DEMO_DAMAGE_SUMMARY,
  DEMO_INCIDENT_BRIEFING,
  DEMO_RECOMMENDATIONS,
  DEMO_RESOURCE_CANDIDATES,
  DEMO_ROAD_RISK,
  DEMO_ROUTE_COMPARISON,
  DEMO_ROUTES,
  DEMO_SEARCH_ZONES,
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
  const [uploadProgress, setUploadProgress] = React.useState<number | null>(null);
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
  const intelligenceContext = useAnalysisIntelligenceContext(
    isDemoMode ? null : activeAnalysisId,
    isCompleted,
  );
  const intelligenceSearchZones = useAnalysisSearchZones(
    isDemoMode ? null : activeAnalysisId,
    isCompleted,
  );
  const intelligenceRecommendations = useAnalysisRecommendations(
    isDemoMode ? null : activeAnalysisId,
    isCompleted,
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

  const isBriefingAvailable = isDemoMode || isCompleted;

  const mapSearchZones = isDemoMode
    ? DEMO_SEARCH_ZONES
    : (intelligenceSearchZones.data?.search_zones ?? null);
  const topCandidate = isDemoMode
    ? DEMO_RESOURCE_CANDIDATES[0]
    : intelligenceRecommendations.data?.resource_candidates[0];
  const mapRecommendedRoute =
    topCandidate?.route_feasibility.status === "computed" ? (topCandidate.route ?? null) : null;

  return (
    <div className="flex flex-1 flex-col gap-4 p-4">
      <IncidentStatusBar
        analysisState={analysisState}
        severity={briefing?.incident_severity ?? null}
        totalStructures={totalStructures}
        isDemoMode={isDemoMode}
      />

      <div className="grid flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="glass-panel relative min-h-[420px] overflow-hidden rounded-xl lg:min-h-0">
          <CommandMapLoader
            damage={damage?.available ? damage.feature_collection : null}
            distanceOnlyRoute={distanceOnlyRoute}
            riskAwareRoute={riskAwareRoute}
            searchZones={mapSearchZones}
            recommendedRoute={mapRecommendedRoute}
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
                className="glass-panel"
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
            className="glass-panel absolute bottom-3 right-3 z-10 lg:hidden"
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
          <AnalysisWorkspace
            isDemoMode={isDemoMode}
            hasActiveAnalysis={activeAnalysisId !== null}
            analysisState={analysisState}
            failure={analysis.data?.failure ?? null}
            uploadProgress={uploadProgress}
            uploadErrorMessage={upload.isError ? upload.error.message : null}
            onFileSelected={(file) => {
              setUploadProgress(null);
              upload.mutate(
                { file, onProgress: (loaded, total) => setUploadProgress(total > 0 ? loaded / total : null) },
                {
                  onSuccess: (result) => {
                    if (result.ok) setActiveAnalysisId(result.data.analysis_id);
                  },
                },
              );
            }}
            onReset={() => {
              setActiveAnalysisId(null);
              setUploadProgress(null);
              upload.reset();
            }}
          />

          <ResultsPanelGrid
            damageStats={{
              summary: damageSummary,
              available: damageSummaryAvailable,
              reason: damageSummaryReason,
              highPriorityCount: briefing?.affected_structures.high_priority_count ?? null,
              isLoading: !isDemoMode && analysis.isLoading,
              isError: !isDemoMode && analysis.isError,
              errorMessage: !isDemoMode ? analysis.error?.message : undefined,
            }}
            roadRisk={{
              edges: roadRiskData?.edges ?? [],
              available: roadRiskData?.available ?? false,
              reason: roadRiskData?.reason ?? null,
              isLoading: !isDemoMode && roadRisk.isLoading && isCompleted,
              isError: !isDemoMode && roadRisk.isError,
              errorMessage: !isDemoMode ? roadRisk.error?.message : undefined,
            }}
            affectedArea={{
              featureCollection: damage?.feature_collection ?? null,
              damageAvailable: damage?.available ?? false,
              damageReason: damage?.reason ?? null,
              isDamageLoading: !isDemoMode && damageMap.isLoading && isCompleted,
              isDamageError: !isDemoMode && damageMap.isError,
              damageErrorMessage: !isDemoMode ? damageMap.error?.message : undefined,
              priorityArea: briefing?.priority_area ?? null,
              isBriefingAvailable,
            }}
            routeComparison={{
              comparison: isDemoMode ? DEMO_ROUTE_COMPARISON : (routeComparison.data ?? null),
              hasSelectedPoints: isDemoMode || (routeStart !== null && routeDestination !== null),
              isLoading: !isDemoMode && routeComparison.isLoading,
              isError: !isDemoMode && routeComparison.isError,
              errorMessage: !isDemoMode ? routeComparison.error?.message : undefined,
            }}
            intelligence={{
              contextAvailable: isDemoMode || (intelligenceContext.data?.context_available ?? false),
              contextUnavailableReason: isDemoMode
                ? null
                : (intelligenceContext.data?.context_unavailable_reason ?? null),
              isSimulated: isDemoMode,
              searchZones: isDemoMode
                ? DEMO_SEARCH_ZONES
                : (intelligenceSearchZones.data?.search_zones ?? []),
              isSearchZonesLoading: !isDemoMode && intelligenceSearchZones.isLoading && isCompleted,
              isSearchZonesError: !isDemoMode && intelligenceSearchZones.isError,
              searchZonesErrorMessage: !isDemoMode ? intelligenceSearchZones.error?.message : undefined,
              recommendations: isDemoMode
                ? DEMO_RECOMMENDATIONS
                : (intelligenceRecommendations.data?.recommendations ?? []),
              isRecommendationsLoading:
                !isDemoMode && intelligenceRecommendations.isLoading && isCompleted,
              isRecommendationsError: !isDemoMode && intelligenceRecommendations.isError,
              recommendationsErrorMessage: !isDemoMode
                ? intelligenceRecommendations.error?.message
                : undefined,
              topSearchZoneId: isDemoMode
                ? (DEMO_SEARCH_ZONES[0]?.id ?? null)
                : (intelligenceRecommendations.data?.top_search_zone_id ?? null),
              resourceView: {
                kind: "candidates",
                candidates: isDemoMode
                  ? DEMO_RESOURCE_CANDIDATES
                  : (intelligenceRecommendations.data?.resource_candidates ?? []),
              } satisfies ResourceView,
              resourcesAreDemo: isDemoMode || (intelligenceRecommendations.data?.resources_are_demo ?? true),
              roadsAvailable: isDemoMode || (intelligenceContext.data?.roads_available ?? false),
              roadsUnavailableReason: isDemoMode
                ? null
                : (intelligenceContext.data?.roads_unavailable_reason ?? null),
            }}
            briefing={{
              briefing: briefing ?? null,
              isLoading: !isDemoMode && summary.isLoading && isCompleted,
              isError: !isDemoMode && summary.isError,
              errorMessage: !isDemoMode ? summary.error?.message : undefined,
              isAvailable: isBriefingAvailable,
              onRegenerate: isDemoMode
                ? undefined
                : () =>
                    regenerate.mutate(
                      routeStart && routeDestination
                        ? { start: routeStart, destination: routeDestination }
                        : undefined,
                    ),
              isRegenerating: regenerate.isPending,
            }}
          />
        </div>
      </div>
    </div>
  );
}

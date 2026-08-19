import type { AffectedAreaPanelProps } from "@/components/command-center/affected-area-panel";
import { AffectedAreaPanel } from "@/components/command-center/affected-area-panel";
import type { BriefingPanelProps } from "@/components/command-center/briefing-panel";
import { BriefingPanel } from "@/components/command-center/briefing-panel";
import type { DamageStatsPanelProps } from "@/components/command-center/damage-stats-panel";
import { DamageStatsPanel } from "@/components/command-center/damage-stats-panel";
import type { RoadRiskPanelProps } from "@/components/command-center/road-risk-panel";
import { RoadRiskPanel } from "@/components/command-center/road-risk-panel";
import type { RouteComparisonPanelProps } from "@/components/command-center/route-comparison-panel";
import { RouteComparisonPanel } from "@/components/command-center/route-comparison-panel";

export interface ResultsPanelGridProps {
  damageStats: Omit<DamageStatsPanelProps, "className">;
  roadRisk: Omit<RoadRiskPanelProps, "className">;
  affectedArea: Omit<AffectedAreaPanelProps, "className">;
  routeComparison: Omit<RouteComparisonPanelProps, "className">;
  briefing: Omit<BriefingPanelProps, "className">;
}

/**
 * Orders the results half of the flow — Damage Intelligence -> Risk
 * Assessment -> Affected Area -> Rescue Accessibility -> AI Incident
 * Brief — per the milestone's requested section order (desktop, via the
 * `lg:order-*` values below). Every panel keeps its existing,
 * independently-tested prop contract; this component only arranges them.
 * Each panel auto-populates on its own as soon as its own data becomes
 * available (no wizard, no click required to "advance") — see
 * `docs/architecture/frontend.md`, "Data flow".
 *
 * Renders a Fragment, not a wrapping `<div>`: the panels need to be true
 * DOM siblings of `analysis-workspace.tsx`'s block (both are direct
 * children of `command-center.tsx`'s info rail) so the mobile
 * `order-*`/`lg:order-*` pair on every panel here can reprioritize
 * Risk/Route/Briefing above the upload/analysis block on small screens —
 * `order` only reorders true siblings, not nested component trees. See
 * "Responsive design" in the architecture doc for the full mobile
 * priority list and its disclosed DOM/tab-order trade-off.
 */
export function ResultsPanelGrid({
  damageStats,
  roadRisk,
  affectedArea,
  routeComparison,
  briefing,
}: ResultsPanelGridProps) {
  return (
    <>
      <DamageStatsPanel {...damageStats} className="order-5 lg:order-2" />
      <RoadRiskPanel {...roadRisk} className="order-1 lg:order-3" />
      <AffectedAreaPanel {...affectedArea} className="order-6 lg:order-4" />
      <RouteComparisonPanel {...routeComparison} className="order-2 lg:order-5" />
      <BriefingPanel {...briefing} className="order-3 lg:order-6" />
    </>
  );
}

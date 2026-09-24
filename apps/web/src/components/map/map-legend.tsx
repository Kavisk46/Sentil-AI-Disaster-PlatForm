import {
  DAMAGE_CLASS_STYLE,
  RESOURCE_AVAILABILITY_STYLE,
  ROUTE_MODE_STYLE,
  SEARCH_PRIORITY_STYLE,
} from "@/lib/risk-colors";

const DAMAGE_ORDER = ["no_damage", "minor", "major", "destroyed"] as const;
const SEARCH_PRIORITY_ORDER = ["low", "moderate", "high", "critical"] as const;
const RESOURCE_AVAILABILITY_ORDER = ["available", "deployed", "unavailable"] as const;

export interface MapLegendProps {
  /** Whether any resource markers are currently plotted — hides the
   * "Resources" section entirely rather than showing an empty legend
   * entry for a layer with nothing on it. */
  showResources?: boolean;
  /**
   * F6.1: honest disclosure that hazard/infrastructure *counts* exist
   * (`AnalysisIntelligenceContextResponse.hazard_count`/
   * `infrastructure_count`) but cannot be plotted — no endpoint in this
   * milestone exposes their geometry (see
   * `docs/architecture/frontend.md`, "Map layers"). `null` hides the row
   * entirely (nothing recorded, nothing to disclose); `0` is shown the
   * same way. This is the "create a strong empty/unavailable state
   * rather than fake geographic objects" requirement, applied here
   * instead of inventing pins with no real coordinates behind them.
   */
  hazardCount?: number | null;
  infrastructureCount?: number | null;
}

/**
 * Every legend entry pairs a color swatch with a short text code (`ND`,
 * `MN`, `MJ`, `DS`, ...) so damage severity is never communicated by
 * color alone — see `lib/risk-colors.ts` and
 * `docs/architecture/frontend.md`, "Accessibility decisions".
 */
export function MapLegend({
  showResources = false,
  hazardCount = null,
  infrastructureCount = null,
}: MapLegendProps) {
  const hasHazardInfo = hazardCount !== null || infrastructureCount !== null;
  return (
    <div className="glass-panel pointer-events-none absolute bottom-3 left-3 z-10 flex flex-col gap-2 rounded-lg p-3 text-xs">
      <div>
        <p className="mb-1 font-semibold tracking-wide text-muted-foreground">Damage</p>
        <ul className="flex flex-col gap-0.5">
          {DAMAGE_ORDER.map((key) => {
            const style = DAMAGE_CLASS_STYLE[key];
            return (
              <li key={key} className="flex items-center gap-1.5">
                <span
                  className="inline-block size-2.5 rounded-full border border-white/20"
                  style={{ backgroundColor: style.hex }}
                />
                <span className="font-mono text-[10px] text-muted-foreground">{style.code}</span>
                <span>{style.label}</span>
              </li>
            );
          })}
        </ul>
      </div>
      <div>
        <p className="mb-1 font-semibold tracking-wide text-muted-foreground">Route</p>
        <ul className="flex flex-col gap-0.5">
          <li className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 rounded" style={{ backgroundColor: ROUTE_MODE_STYLE.risk_aware.hex }} />
            <span>{ROUTE_MODE_STYLE.risk_aware.label} (selected)</span>
          </li>
          <li className="flex items-center gap-1.5">
            <span
              className="inline-block h-0.5 w-4 rounded border-t border-dashed"
              style={{ borderColor: ROUTE_MODE_STYLE.distance_only.hex }}
            />
            <span>{ROUTE_MODE_STYLE.distance_only.label} (baseline)</span>
          </li>
          <li className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 rounded border-t border-dashed" style={{ borderColor: "#d946ef" }} />
            <span>Recommended (to top zone)</span>
          </li>
        </ul>
      </div>
      <div>
        <p className="mb-1 font-semibold tracking-wide text-muted-foreground">Search priority</p>
        <ul className="flex flex-col gap-0.5">
          {SEARCH_PRIORITY_ORDER.map((key) => {
            const style = SEARCH_PRIORITY_STYLE[key];
            return (
              <li key={key} className="flex items-center gap-1.5">
                <span
                  className="inline-block size-2.5 rounded-full border border-white/20"
                  style={{ backgroundColor: style.hex }}
                />
                <span className="font-mono text-[10px] text-muted-foreground">{style.code}</span>
                <span>{style.label}</span>
              </li>
            );
          })}
        </ul>
      </div>
      {showResources && (
        <div>
          <p className="mb-1 font-semibold tracking-wide text-muted-foreground">Resources</p>
          <ul className="flex flex-col gap-0.5">
            {RESOURCE_AVAILABILITY_ORDER.map((key) => {
              const style = RESOURCE_AVAILABILITY_STYLE[key];
              return (
                <li key={key} className="flex items-center gap-1.5">
                  <span
                    className="inline-block size-2.5 rounded-full border border-white/40"
                    style={{ backgroundColor: style.hex }}
                  />
                  <span className="font-mono text-[10px] text-muted-foreground">{style.code}</span>
                  <span>{style.label}</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {hasHazardInfo && (
        <div className="border-border/40 border-t pt-2">
          <p className="mb-1 font-semibold tracking-wide text-muted-foreground">
            Hazards &amp; infrastructure
          </p>
          <p className="text-muted-foreground max-w-40">
            {hazardCount ?? 0} hazard(s), {infrastructureCount ?? 0} infrastructure record(s) —
            not shown on the map (no geometry available).
          </p>
        </div>
      )}
    </div>
  );
}

import { DAMAGE_CLASS_STYLE, ROUTE_MODE_STYLE, SEARCH_PRIORITY_STYLE } from "@/lib/risk-colors";

const DAMAGE_ORDER = ["no_damage", "minor", "major", "destroyed"] as const;
const SEARCH_PRIORITY_ORDER = ["low", "moderate", "high", "critical"] as const;

/**
 * Every legend entry pairs a color swatch with a short text code (`ND`,
 * `MN`, `MJ`, `DS`, ...) so damage severity is never communicated by
 * color alone — see `lib/risk-colors.ts` and
 * `docs/architecture/frontend.md`, "Accessibility decisions".
 */
export function MapLegend() {
  return (
    <div
      className="pointer-events-none absolute bottom-3 left-3 z-10 flex flex-col gap-2 rounded-lg border border-white/10 bg-background/70 p-3 text-xs backdrop-blur-md"
    >
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
    </div>
  );
}

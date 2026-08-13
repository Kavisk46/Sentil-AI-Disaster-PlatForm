import type { DamageSummary } from "@sentinelai/shared";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { deriveDamageBreakdown } from "@/lib/damage";
import { DAMAGE_CLASS_STYLE } from "@/lib/risk-colors";

const DAMAGE_ORDER = ["no_damage", "minor", "major", "destroyed"] as const;

export interface DamageStatsPanelProps {
  summary: DamageSummary | null;
  available: boolean;
  reason: string | null;
  highPriorityCount: number | null;
  isLoading: boolean;
  isError: boolean;
  errorMessage?: string;
  className?: string;
}

export function DamageStatsPanel({
  summary,
  available,
  reason,
  highPriorityCount,
  isLoading,
  isError,
  errorMessage,
  className,
}: DamageStatsPanelProps) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Damage distribution</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        )}

        {!isLoading && isError && (
          <Alert variant="destructive">
            <AlertTitle>Damage data unavailable</AlertTitle>
            <AlertDescription>{errorMessage ?? "The backend could not be reached."}</AlertDescription>
          </Alert>
        )}

        {!isLoading && !isError && (!available || !summary) && (
          <p className="text-muted-foreground text-sm">
            {reason ?? "No damage assessment is available for this analysis yet."}
          </p>
        )}

        {!isLoading && !isError && available && summary && (
          <div className="flex flex-col gap-3">
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-semibold tabular-nums">{summary.total_buildings}</span>
              <span className="text-muted-foreground text-xs">structures assessed</span>
            </div>

            <div
              className="flex h-2.5 w-full overflow-hidden rounded-full bg-muted"
              role="img"
              aria-label={`Damage breakdown: ${DAMAGE_ORDER.map(
                (key) => `${DAMAGE_CLASS_STYLE[key].label} ${deriveDamageBreakdown(summary)[key]}`,
              ).join(", ")}`}
            >
              {DAMAGE_ORDER.map((key) => {
                const count = deriveDamageBreakdown(summary)[key];
                const pct = summary.total_buildings > 0 ? (count / summary.total_buildings) * 100 : 0;
                if (pct === 0) return null;
                return (
                  <span
                    key={key}
                    style={{ width: `${pct}%`, backgroundColor: DAMAGE_CLASS_STYLE[key].hex }}
                    className="h-full first:rounded-l-full last:rounded-r-full"
                  />
                );
              })}
            </div>

            <ul className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
              {DAMAGE_ORDER.map((key) => {
                const style = DAMAGE_CLASS_STYLE[key];
                const count = deriveDamageBreakdown(summary)[key];
                return (
                  <li key={key} className="flex items-center gap-1.5">
                    <span
                      className="inline-block size-2 rounded-full"
                      style={{ backgroundColor: style.hex }}
                      aria-hidden="true"
                    />
                    <span className="font-mono text-[10px] text-muted-foreground">{style.code}</span>
                    <span>{style.label}</span>
                    <span className="ml-auto tabular-nums font-medium">{count}</span>
                  </li>
                );
              })}
            </ul>

            {highPriorityCount !== null && (
              <p className="text-muted-foreground text-xs">
                <span className="font-medium text-foreground">{highPriorityCount}</span> high-priority
                structure(s) identified.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

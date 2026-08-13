import { TrendingDown } from "lucide-react";
import type { RouteComparison } from "@sentinelai/shared";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDistanceMeters, formatPercent, formatRiskScore } from "@/lib/geo";
import { ROUTE_MODE_STYLE } from "@/lib/risk-colors";

export interface RouteComparisonPanelProps {
  comparison: RouteComparison | null;
  hasSelectedPoints: boolean;
  isLoading: boolean;
  isError: boolean;
  errorMessage?: string;
  className?: string;
}

function RouteResultCard({
  label,
  color,
  distance,
  risk,
  cost,
  found,
  reason,
}: {
  label: string;
  color: string;
  distance: number | null;
  risk: number | null;
  cost: number | null;
  found: boolean;
  reason: string | null;
}) {
  return (
    <div className="flex-1 rounded-lg border border-border/60 p-3">
      <p className="text-xs font-semibold tracking-wide" style={{ color }}>
        {label.toUpperCase()}
      </p>
      {found ? (
        <div className="mt-1.5 flex flex-col gap-0.5">
          <p className="text-lg font-semibold tabular-nums">{formatDistanceMeters(distance)}</p>
          <p className="text-muted-foreground text-xs">Risk: {formatRiskScore(risk)}</p>
          <p className="text-muted-foreground text-xs">Cost: {formatRiskScore(cost)}</p>
        </div>
      ) : (
        <p className="text-muted-foreground mt-1.5 text-xs">{reason ?? "No route found."}</p>
      )}
    </div>
  );
}

/**
 * Every value shown here comes straight from `RouteComparison` (see
 * `lib/geo.ts::computeRouteComparison`) — a client-side derivation of two
 * real `POST /api/v1/routing` responses, never a hard-coded example.
 */
export function RouteComparisonPanel({
  comparison,
  hasSelectedPoints,
  isLoading,
  isError,
  errorMessage,
  className,
}: RouteComparisonPanelProps) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Route comparison</CardTitle>
      </CardHeader>
      <CardContent>
        {!hasSelectedPoints && !isLoading && (
          <p className="text-muted-foreground text-sm">
            Click the map to set a start and destination point, then compare routes.
          </p>
        )}

        {hasSelectedPoints && isLoading && (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        )}

        {hasSelectedPoints && !isLoading && isError && (
          <Alert variant="destructive">
            <AlertTitle>Route unavailable</AlertTitle>
            <AlertDescription>{errorMessage ?? "The backend could not be reached."}</AlertDescription>
          </Alert>
        )}

        {hasSelectedPoints && !isLoading && !isError && comparison && (
          <div className="flex flex-col gap-3">
            <div className="flex gap-2">
              <RouteResultCard
                label="Distance only"
                color={ROUTE_MODE_STYLE.distance_only.hex}
                distance={comparison.distanceOnly.total_distance}
                risk={comparison.distanceOnly.accumulated_risk}
                cost={comparison.distanceOnly.total_cost}
                found={comparison.distanceOnly.found}
                reason={comparison.distanceOnly.reason}
              />
              <RouteResultCard
                label="Risk aware"
                color={ROUTE_MODE_STYLE.risk_aware.hex}
                distance={comparison.riskAware.total_distance}
                risk={comparison.riskAware.accumulated_risk}
                cost={comparison.riskAware.total_cost}
                found={comparison.riskAware.found}
                reason={comparison.riskAware.reason}
              />
            </div>

            <div className="flex items-center justify-between rounded-lg border border-border/60 px-3 py-2 text-sm">
              <span className="flex items-center gap-1.5 text-muted-foreground">
                <TrendingDown className="size-3.5 text-emerald-400" aria-hidden="true" />
                Risk reduction
              </span>
              <span className="font-semibold tabular-nums text-emerald-400">
                {formatPercent(comparison.riskReduction)}
              </span>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border/60 px-3 py-2 text-sm">
              <span className="text-muted-foreground">Detour</span>
              <span className="font-semibold tabular-nums">
                {comparison.detourRatio === null ? "—" : formatPercent(comparison.detourRatio - 1)}
              </span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

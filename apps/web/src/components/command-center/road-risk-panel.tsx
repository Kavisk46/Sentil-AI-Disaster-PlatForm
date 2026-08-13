import type { RiskLevel, RoadEdge } from "@sentinelai/shared";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ACCESSIBILITY_STYLE, RISK_LEVEL_STYLE } from "@/lib/risk-colors";

const RISK_ORDER: RiskLevel[] = ["critical", "high", "moderate", "low"];
const MAX_LISTED_EDGES = 25;

export interface RoadRiskPanelProps {
  edges: RoadEdge[];
  available: boolean;
  reason: string | null;
  isLoading: boolean;
  isError: boolean;
  errorMessage?: string;
  className?: string;
}

function edgeLabel(edge: RoadEdge): string {
  return edge.name ?? `${edge.source_node} → ${edge.target_node}`;
}

/**
 * Road risk and road accessibility are rendered as two visually distinct
 * badges per edge — never merged into one indicator — so a `critical`-risk
 * edge that happens to still be `open` (or a `low`-risk edge that's
 * `blocked` for an unrelated reason) is never misread as the other. See
 * `lib/risk-colors.ts` for the shared rationale, and
 * `docs/architecture/frontend.md`, "Road-risk visualization", for why this
 * is a list rather than a map layer (the backend doesn't expose node
 * coordinates outside of a computed route).
 */
export function RoadRiskPanel({
  edges,
  available,
  reason,
  isLoading,
  isError,
  errorMessage,
  className,
}: RoadRiskPanelProps) {
  const counts = RISK_ORDER.reduce(
    (acc, level) => {
      acc[level] = edges.filter((edge) => edge.risk_level === level).length;
      return acc;
    },
    {} as Record<RiskLevel, number>,
  );

  const sorted = [...edges].sort((a, b) => {
    const rank = (level: RiskLevel | null) => (level ? RISK_ORDER.indexOf(level) : RISK_ORDER.length);
    return rank(a.risk_level) - rank(b.risk_level);
  });

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Road risk</CardTitle>
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
            <AlertTitle>Road risk data unavailable</AlertTitle>
            <AlertDescription>{errorMessage ?? "The backend could not be reached."}</AlertDescription>
          </Alert>
        )}

        {!isLoading && !isError && !available && (
          <p className="text-muted-foreground text-sm">
            {reason ?? "No road risk assessment is available for this analysis yet."}
          </p>
        )}

        {!isLoading && !isError && available && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-1.5">
              {RISK_ORDER.map((level) => (
                <Badge key={level} variant="outline" className={RISK_LEVEL_STYLE[level].className}>
                  {RISK_LEVEL_STYLE[level].code} {RISK_LEVEL_STYLE[level].label}: {counts[level]}
                </Badge>
              ))}
            </div>

            {edges.length === 0 ? (
              <p className="text-muted-foreground text-sm">No road segments were assessed.</p>
            ) : (
              <ul className="flex max-h-56 flex-col gap-1.5 overflow-y-auto pr-1">
                {sorted.slice(0, MAX_LISTED_EDGES).map((edge, index) => (
                  <li
                    key={`${edge.source_node}-${edge.target_node}-${index}`}
                    className="flex items-center justify-between gap-2 rounded-md border border-border/60 px-2 py-1.5 text-xs"
                  >
                    <span className="truncate">{edgeLabel(edge)}</span>
                    <span className="flex shrink-0 gap-1">
                      <Badge
                        variant="outline"
                        className={edge.risk_level ? RISK_LEVEL_STYLE[edge.risk_level].className : ""}
                      >
                        {edge.risk_level ? RISK_LEVEL_STYLE[edge.risk_level].code : "—"}
                      </Badge>
                      <Badge variant="outline" className={ACCESSIBILITY_STYLE[edge.accessibility].className}>
                        {ACCESSIBILITY_STYLE[edge.accessibility].code}
                      </Badge>
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {edges.length > MAX_LISTED_EDGES && (
              <p className="text-muted-foreground text-xs">
                +{edges.length - MAX_LISTED_EDGES} more segment(s) not shown.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

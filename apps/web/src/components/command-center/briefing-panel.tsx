import { Bot, RefreshCw } from "lucide-react";
import type { IncidentBriefing } from "@sentinelai/shared";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { CONFIDENCE_STYLE, INCIDENT_SEVERITY_STYLE } from "@/lib/risk-colors";

export interface BriefingPanelProps {
  briefing: IncidentBriefing | null;
  isLoading: boolean;
  isError: boolean;
  errorMessage?: string;
  isAvailable: boolean;
  onRegenerate?: () => void;
  isRegenerating?: boolean;
  className?: string;
}

/**
 * Always labeled "AI-GENERATED INCIDENT BRIEFING" and always shows the
 * backend's own fixed safety disclaimer — this panel never implies the
 * summary is an authoritative emergency command (see
 * `apps/api/app/incident/briefing_builder.py`, `_DISCLAIMER`, and
 * `docs/architecture/frontend.md`, "AI briefing").
 */
export function BriefingPanel({
  briefing,
  isLoading,
  isError,
  errorMessage,
  isAvailable,
  onRegenerate,
  isRegenerating,
  className,
}: BriefingPanelProps) {
  return (
    <Card className={className}>
      <CardHeader className="flex-row items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Bot className="size-4 text-sky-400" aria-hidden="true" />
          <CardTitle>AI-Generated Incident Briefing</CardTitle>
        </div>
        {briefing && onRegenerate && (
          <Button
            variant="ghost"
            size="icon"
            aria-label="Regenerate briefing"
            onClick={onRegenerate}
            disabled={isRegenerating}
          >
            <RefreshCw className={`size-4 ${isRegenerating ? "motion-safe:animate-spin" : ""}`} />
          </Button>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {isLoading && (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-16 w-full" />
          </div>
        )}

        {!isLoading && isError && (
          <Alert variant="destructive">
            <AlertTitle>Briefing unavailable</AlertTitle>
            <AlertDescription>{errorMessage ?? "The backend could not be reached."}</AlertDescription>
          </Alert>
        )}

        {!isLoading && !isError && !isAvailable && (
          <p className="text-muted-foreground text-sm">
            A briefing will be generated once the analysis is complete.
          </p>
        )}

        {!isLoading && !isError && briefing && (
          <>
            <div className="flex flex-wrap gap-1.5">
              <Badge
                variant="outline"
                className={INCIDENT_SEVERITY_STYLE[briefing.incident_severity].className}
              >
                Severity: {INCIDENT_SEVERITY_STYLE[briefing.incident_severity].label}
              </Badge>
              <Badge variant="outline" className={CONFIDENCE_STYLE[briefing.confidence].className}>
                Confidence: {CONFIDENCE_STYLE[briefing.confidence].label}
              </Badge>
            </div>

            <dl className="grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded-md border border-border/60 p-2">
                <dt className="text-muted-foreground">Total</dt>
                <dd className="text-base font-semibold tabular-nums">
                  {briefing.affected_structures.total}
                </dd>
              </div>
              <div className="rounded-md border border-border/60 p-2">
                <dt className="text-muted-foreground">Destroyed</dt>
                <dd className="text-base font-semibold tabular-nums">
                  {briefing.affected_structures.destroyed}
                </dd>
              </div>
              <div className="rounded-md border border-border/60 p-2">
                <dt className="text-muted-foreground">High priority</dt>
                <dd className="text-base font-semibold tabular-nums">
                  {briefing.affected_structures.high_priority_count}
                </dd>
              </div>
            </dl>

            <div className="flex flex-col gap-2 text-sm">
              <div>
                <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide">
                  Priority area
                </p>
                <p>{briefing.priority_area}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide">
                  Route summary
                </p>
                <p>{briefing.route_summary}</p>
              </div>
              {briefing.key_findings.length > 0 && (
                <div>
                  <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide">
                    Key findings
                  </p>
                  <ul className="list-inside list-disc">
                    {briefing.key_findings.map((finding, index) => (
                      <li key={index}>{finding}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {briefing.limitations.length > 0 && (
              <div className="text-muted-foreground text-xs">
                <p className="font-medium uppercase tracking-wide">Limitations</p>
                <ul className="list-inside list-disc">
                  {briefing.limitations.map((limitation, index) => (
                    <li key={index}>{limitation}</li>
                  ))}
                </ul>
              </div>
            )}

            <p className="text-muted-foreground border-t border-border/60 pt-2 text-[11px] leading-relaxed">
              {briefing.disclaimer}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

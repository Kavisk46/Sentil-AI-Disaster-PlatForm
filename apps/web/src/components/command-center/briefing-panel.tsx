import { Bot, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import type { IncidentBriefing } from "@sentinelai/shared";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProvenanceBadge } from "@/components/ui/provenance-badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { ProvenanceCategory } from "@/lib/data-provenance";
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

function Section({
  heading,
  provenance,
  children,
}: {
  heading: string;
  provenance: ProvenanceCategory;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">{heading}</h4>
        <ProvenanceBadge category={provenance} />
      </div>
      {children}
    </section>
  );
}

/** The honest "this spec section has no backend equivalent" state — same
 * muted/dashed visual language as `analysis-stage-tracker.tsx`'s "Not yet
 * available" rows, applied here to sections the backend simply doesn't
 * expose at all (as opposed to "not yet" — it never will, under the
 * current API contract). Never filled with synthesized-sounding text. */
function NotExposed({ reason }: { reason: string }) {
  return (
    <p className="text-muted-foreground flex items-center gap-1.5 text-sm">
      <span className="border-muted-foreground/40 rounded border border-dashed px-1 py-px text-[10px] font-medium tracking-wide uppercase">
        N/A
      </span>
      Not exposed by the backend — {reason}
    </p>
  );
}

/**
 * Always labeled "AI-Generated Incident Briefing" and always shows the
 * backend's own fixed safety disclaimer — this panel never implies the
 * summary is an authoritative emergency command (see
 * `apps/api/app/incident/briefing_builder.py`, `_DISCLAIMER`, and
 * `docs/architecture/frontend.md`, "AI briefing").
 *
 * Structured into the sections the milestone brief requests (Situation /
 * Affected Areas / Major Risks / Recommended Route / Reasoning / Data
 * Confidence / Limitations), each honestly mapped onto — or, for two of
 * them, honestly *not* mapped onto — the real `IncidentBriefing` fields.
 * See "AI briefing" in the architecture doc for the full mapping table
 * and why `key_findings` keeps its own real heading instead of being
 * folded into "Major Risks".
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
      <CardContent className="flex flex-col gap-4">
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
            {/* Severity/confidence/affected-structure counts are computed
                deterministically server-side from real damage data — never
                from the LLM (see `apps/api/app/incident/severity.py`) — so
                they're labeled "calculated", not "generated". */}
            <Section heading="Situation" provenance="calculated">
              <div className="flex flex-wrap gap-1.5">
                <Badge
                  variant="outline"
                  className={INCIDENT_SEVERITY_STYLE[briefing.incident_severity].className}
                >
                  Severity: {INCIDENT_SEVERITY_STYLE[briefing.incident_severity].label}
                </Badge>
              </div>
              <dl className="mt-2 grid grid-cols-3 gap-2 text-center text-xs">
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
            </Section>

            <Section heading="Affected areas" provenance="generated">
              <p className="text-sm">{briefing.priority_area}</p>
            </Section>

            <Section heading="Major risks" provenance="generated">
              <NotExposed reason="incident briefings do not include a separate hazard/risk enumeration. See Key findings below, and the Risk Assessment section for measured road-risk data." />
            </Section>

            {briefing.key_findings.length > 0 && (
              <Section heading="Key findings" provenance="generated">
                <ul className="list-inside list-disc text-sm">
                  {briefing.key_findings.map((finding, index) => (
                    <li key={index}>{finding}</li>
                  ))}
                </ul>
              </Section>
            )}

            <Section heading="Recommended route" provenance="generated">
              <p className="text-sm">{briefing.route_summary}</p>
              <p className="text-muted-foreground mt-1 text-xs">
                See the Rescue Accessibility section for measured distance/risk numbers.
              </p>
            </Section>

            <Section heading="Reasoning" provenance="generated">
              <NotExposed reason="the backend does not return a separate reasoning trace alongside its conclusions." />
            </Section>

            <Section heading="Data confidence" provenance="calculated">
              <Badge variant="outline" className={CONFIDENCE_STYLE[briefing.confidence].className}>
                Confidence: {CONFIDENCE_STYLE[briefing.confidence].label}
              </Badge>
              <p className="text-muted-foreground mt-1 text-xs">
                Reported as a category only — the backend does not return a numeric confidence score.
              </p>
            </Section>

            {briefing.limitations.length > 0 && (
              <Section heading="Limitations" provenance="generated">
                <ul className="list-inside list-disc text-sm">
                  {briefing.limitations.map((limitation, index) => (
                    <li key={index}>{limitation}</li>
                  ))}
                </ul>
              </Section>
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

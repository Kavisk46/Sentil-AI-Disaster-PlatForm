import { AlertTriangle, CheckCircle2, Circle, Loader2, MinusCircle } from "lucide-react";
import type { AnalysisFailure } from "@sentinelai/shared";

import type { ClientAnalysisState } from "@/components/command-center/analysis-state";
import { cn } from "@/lib/utils";

export interface AnalysisStageTrackerProps {
  analysisState: ClientAnalysisState;
  failure: AnalysisFailure | null;
  className?: string;
}

type RowStatus = "pending" | "in-progress" | "complete" | "failed" | "unavailable";

interface Row {
  label: string;
  status: RowStatus;
  detail: string;
}

/**
 * The milestone brief asks for a 7-stage list (Image received /
 * Preprocessing / Damage analysis / Spatial analysis / Risk assessment /
 * Route optimization / Incident briefing). This component intentionally
 * renders only the first three.
 *
 * Risk assessment, Route optimization, and Incident briefing are NOT
 * sequential sub-stages of one backend pipeline — they're three
 * independently-fetched resources (`useRoadRisk`/`useRouteComparison`/
 * `useIncidentSummary`), all gated on the same single condition
 * (`status === "completed"`), not on each other. Cramming three parallel
 * resources into one linear progress bar would misrepresent the
 * architecture (a responder could reasonably read "Route optimization:
 * not yet available" as "the backend hasn't gotten there yet", when in
 * fact routing is available immediately once an analysis completes — it
 * just needs the user to pick two map points first). Each of those three
 * already has its own honest `available`/`reason` state on its own panel
 * — that's where their readiness belongs. See
 * `docs/architecture/frontend.md`, "Analysis stage tracking".
 *
 * "Spatial analysis" (georeferencing damage geometry) is folded into
 * "Damage analysis" below: it's an attribute of the same
 * `completed`-gated output (`DamageMapResponse`), not a separately
 * timestamped stage — `AnalysisStatus` has no status value for it.
 *
 * "Preprocessing" has no backend signal at all (`AnalysisStatus` jumps
 * straight from `queued` to `processing`) and is always rendered as an
 * honest "Not yet available" row, never a fake completed step.
 */
export function AnalysisStageTracker({ analysisState, failure, className }: AnalysisStageTrackerProps) {
  const imageReceived: RowStatus =
    analysisState === "idle" ? "pending" : analysisState === "uploading" ? "in-progress" : "complete";

  const damageAnalysis: RowStatus =
    analysisState === "failed"
      ? "failed"
      : analysisState === "completed"
        ? "complete"
        : analysisState === "queued" || analysisState === "processing"
          ? "in-progress"
          : "pending";

  const rows: Row[] = [
    {
      label: "Image received",
      status: imageReceived,
      detail:
        imageReceived === "complete"
          ? "Image uploaded to the backend."
          : imageReceived === "in-progress"
            ? "Uploading..."
            : "Waiting for an image.",
    },
    {
      label: "Preprocessing",
      status: "unavailable",
      detail: "Not yet available — the backend does not report a distinct preprocessing stage.",
    },
    {
      label: "Damage analysis",
      status: damageAnalysis,
      detail:
        damageAnalysis === "failed"
          ? (failure?.message ?? "Analysis failed.")
          : damageAnalysis === "complete"
            ? "Damage classification and spatial mapping complete."
            : damageAnalysis === "in-progress"
              ? "Analyzing disaster damage..."
              : "Waiting to start.",
    },
  ];

  return (
    <ol className={cn("flex flex-col gap-2.5", className)}>
      {rows.map((row) => (
        <li key={row.label} className="flex items-start gap-2.5">
          <span className="mt-0.5 shrink-0" aria-hidden="true">
            <StageIcon status={row.status} />
          </span>
          <div>
            <p
              className={cn(
                "flex items-center gap-1.5 text-sm font-medium leading-none",
                row.status === "unavailable" && "text-muted-foreground",
              )}
            >
              {row.label}
              {row.status === "unavailable" && (
                <span className="border-muted-foreground/40 text-muted-foreground rounded border border-dashed px-1 py-px text-[10px] font-normal tracking-wide uppercase">
                  N/A
                </span>
              )}
            </p>
            <p
              className="text-muted-foreground mt-1 text-xs"
              {...(row.label === "Damage analysis" ? { role: "status", "aria-live": "polite" as const } : {})}
            >
              {row.detail}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}

function StageIcon({ status }: { status: RowStatus }) {
  switch (status) {
    case "complete":
      return <CheckCircle2 className="size-4 text-emerald-500" />;
    case "in-progress":
      return <Loader2 className="size-4 motion-safe:animate-spin text-sky-400" />;
    case "failed":
      return <AlertTriangle className="size-4 text-destructive" />;
    case "unavailable":
      return <MinusCircle className="text-muted-foreground/60 size-4" />;
    case "pending":
    default:
      return <Circle className="text-muted-foreground/60 size-4" />;
  }
}

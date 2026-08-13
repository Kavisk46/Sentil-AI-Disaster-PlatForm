import { AlertTriangle, CheckCircle2, Loader2, UploadCloud } from "lucide-react";
import type { AnalysisFailure, AnalysisStatus } from "@sentinelai/shared";

import { cn } from "@/lib/utils";

export type ClientAnalysisState = "idle" | "uploading" | AnalysisStatus;

/**
 * Copy for every *real* state the backend (or the upload request itself)
 * actually reports. The milestone brief's example additionally lists
 * "SPATIAL ANALYSIS"/"ROUTE ANALYSIS" sub-stages — those are not states
 * `AnalysisStatus` (`app/schemas/analysis.py`) exposes today, so they are
 * deliberately not shown here; inventing them would violate "do not fake
 * progress ... unless the backend actually provides them". See
 * `docs/architecture/frontend.md`, "Analysis states", for the full
 * rationale.
 */
const STATE_COPY: Record<ClientAnalysisState, { label: string; description: string }> = {
  idle: { label: "Idle", description: "No image uploaded yet." },
  uploading: { label: "Uploading", description: "Uploading satellite imagery..." },
  uploaded: { label: "Uploaded", description: "Image received, waiting to be queued." },
  queued: { label: "Queued", description: "Queued for damage analysis." },
  processing: { label: "Processing", description: "Analyzing disaster damage..." },
  completed: { label: "Completed", description: "Incident assessment ready." },
  failed: { label: "Failed", description: "Analysis failed." },
};

const ACTIVE_STATES = new Set<ClientAnalysisState>(["uploading", "uploaded", "queued", "processing"]);

export interface AnalysisStateIndicatorProps {
  state: ClientAnalysisState;
  failure?: AnalysisFailure | null;
  className?: string;
}

export function AnalysisStateIndicator({ state, failure, className }: AnalysisStateIndicatorProps) {
  const copy = STATE_COPY[state];
  const isActive = ACTIVE_STATES.has(state);

  return (
    <div className={cn("flex items-start gap-2.5", className)} role="status" aria-live="polite">
      <span className="mt-0.5 shrink-0" aria-hidden="true">
        {state === "failed" && <AlertTriangle className="size-4 text-destructive" />}
        {state === "completed" && <CheckCircle2 className="size-4 text-emerald-500" />}
        {isActive && <Loader2 className="size-4 motion-safe:animate-spin text-sky-400" />}
        {state === "idle" && <UploadCloud className="size-4 text-muted-foreground" />}
      </span>
      <div>
        <p className="text-sm font-medium leading-none">{copy.label}</p>
        <p className="text-muted-foreground mt-1 text-xs">
          {state === "failed" && failure ? failure.message : copy.description}
        </p>
      </div>
    </div>
  );
}

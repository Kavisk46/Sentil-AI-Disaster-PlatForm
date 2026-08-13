import type { IncidentSeverity } from "@sentinelai/shared";

import { Badge } from "@/components/ui/badge";
import type { ClientAnalysisState } from "@/components/command-center/analysis-state";
import { INCIDENT_SEVERITY_STYLE } from "@/lib/risk-colors";

const STATE_LABEL: Record<ClientAnalysisState, string> = {
  idle: "Awaiting upload",
  uploading: "Uploading",
  uploaded: "Uploaded",
  queued: "Queued",
  processing: "Processing",
  completed: "Analysis complete",
  failed: "Analysis failed",
};

export interface IncidentStatusBarProps {
  analysisState: ClientAnalysisState;
  severity: IncidentSeverity | null;
  totalStructures: number | null;
  isDemoMode: boolean;
}

/**
 * The single highest-priority glance strip — incident severity is always
 * the first thing shown per the milestone's visual-hierarchy requirement
 * (see `docs/architecture/frontend.md`, "Visual hierarchy").
 */
export function IncidentStatusBar({
  analysisState,
  severity,
  totalStructures,
  isDemoMode,
}: IncidentStatusBarProps) {
  const severityStyle = severity ? INCIDENT_SEVERITY_STYLE[severity] : null;

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-white/10 bg-card/60 px-4 py-2.5 backdrop-blur-md">
      {isDemoMode && (
        <Badge className="border-amber-500/40 bg-amber-500/15 text-amber-400" variant="outline">
          Demo mode
        </Badge>
      )}

      <span className="text-sm font-medium">Incident severity:</span>
      {severityStyle ? (
        <Badge variant="outline" className={severityStyle.className}>
          {severityStyle.code} {severityStyle.label.toUpperCase()}
        </Badge>
      ) : (
        <span className="text-muted-foreground text-sm">—</span>
      )}

      <span className="text-border mx-1" aria-hidden="true">
        |
      </span>

      <span className="text-muted-foreground text-sm">{STATE_LABEL[analysisState]}</span>

      {totalStructures !== null && (
        <>
          <span className="text-border mx-1" aria-hidden="true">
            |
          </span>
          <span className="text-muted-foreground text-sm">
            <span className="text-foreground font-medium">{totalStructures}</span> structures assessed
          </span>
        </>
      )}
    </div>
  );
}

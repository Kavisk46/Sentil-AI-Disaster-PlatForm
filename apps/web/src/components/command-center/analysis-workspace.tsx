import type { AnalysisFailure } from "@sentinelai/shared";

import type { ClientAnalysisState } from "@/components/command-center/analysis-state";
import { AnalysisStageTracker } from "@/components/command-center/analysis-stage-tracker";
import { UploadPanel } from "@/components/command-center/upload-panel";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface AnalysisWorkspaceProps {
  isDemoMode: boolean;
  hasActiveAnalysis: boolean;
  analysisState: ClientAnalysisState;
  failure: AnalysisFailure | null;
  uploadProgress: number | null;
  uploadErrorMessage: string | null;
  onFileSelected: (file: File) => void;
  onReset: () => void;
  className?: string;
}

/**
 * The "Upload" and "Analysis" stages of the flow, grouped together at the
 * top of the info rail (see `docs/architecture/frontend.md`, "Data
 * flow") — still purely presentational, driven entirely by props from
 * `command-center.tsx`. The stage tracker is skipped in demo mode: demo
 * data trivially reports `analysisState="completed"` (see
 * `lib/demo/demo-data.ts`), and the always-visible "Demo mode" badge on
 * `IncidentStatusBar` already makes the substitution clear elsewhere —
 * a granular real-pipeline tracker would just show two checkmarks and add
 * noise, not information.
 */
export function AnalysisWorkspace({
  isDemoMode,
  hasActiveAnalysis,
  analysisState,
  failure,
  uploadProgress,
  uploadErrorMessage,
  onFileSelected,
  onReset,
  className,
}: AnalysisWorkspaceProps) {
  return (
    // Moves as one unit in the mobile priority reorder below — see
    // `docs/architecture/frontend.md`, "Responsive design".
    <div className={cn("order-4 flex flex-col gap-4 lg:order-1", className)}>
      <UploadPanel
        isDemoMode={isDemoMode}
        hasActiveAnalysis={hasActiveAnalysis}
        state={analysisState}
        failure={failure}
        uploadProgress={uploadProgress}
        uploadErrorMessage={uploadErrorMessage}
        onFileSelected={onFileSelected}
        onReset={onReset}
      />

      {!isDemoMode && hasActiveAnalysis && (
        <Card>
          <CardHeader>
            <CardTitle>Analysis progress</CardTitle>
          </CardHeader>
          <CardContent>
            <AnalysisStageTracker analysisState={analysisState} failure={failure} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

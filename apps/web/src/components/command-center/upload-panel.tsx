"use client";

import { RotateCcw } from "lucide-react";
import type { AnalysisFailure } from "@sentinelai/shared";

import { AnalysisStateIndicator, type ClientAnalysisState } from "@/components/command-center/analysis-state";
import { UploadDropzone } from "@/components/command-center/upload-dropzone";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface UploadPanelProps {
  isDemoMode: boolean;
  hasActiveAnalysis: boolean;
  state: ClientAnalysisState;
  failure: AnalysisFailure | null;
  uploadProgress: number | null;
  uploadErrorMessage: string | null;
  onFileSelected: (file: File) => void;
  onReset: () => void;
  className?: string;
}

/**
 * The upload flow the milestone specifies: select/drop an image ->
 * validate -> upload -> automatically start polling analysis status ->
 * results. No intermediate confirmation step and no manual "start
 * analysis" button — dropping a valid file uploads it immediately.
 * Purely presentational: all data-fetching lives in
 * `command-center.tsx` (the single owner of every hook), passed down as
 * props — see `docs/architecture/frontend.md`, "Frontend architecture".
 * The dropzone itself (drag/drop, validation, preview, progress, retry)
 * is `upload-dropzone.tsx`, shared with the landing page.
 */
export function UploadPanel({
  isDemoMode,
  hasActiveAnalysis,
  state,
  failure,
  uploadProgress,
  uploadErrorMessage,
  onFileSelected,
  onReset,
  className,
}: UploadPanelProps) {
  const isBusy = state !== "idle" && state !== "completed" && state !== "failed";

  if (isDemoMode) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>Analysis controls</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground text-sm">
            Demo mode is active — upload is disabled. Turn off demo mode to analyze a real image.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Analysis controls</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {!hasActiveAnalysis || state === "failed" ? (
          <UploadDropzone
            variant="compact"
            isUploading={state === "uploading"}
            uploadProgress={uploadProgress}
            uploadErrorMessage={uploadErrorMessage}
            onFileSelected={onFileSelected}
          />
        ) : (
          <AnalysisStateIndicator state={state} failure={failure} />
        )}

        {hasActiveAnalysis && !isBusy && (
          <Button variant="outline" size="sm" onClick={onReset}>
            <RotateCcw className="size-3.5" />
            New analysis
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

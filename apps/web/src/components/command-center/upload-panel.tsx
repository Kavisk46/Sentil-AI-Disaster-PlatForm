"use client";

import * as React from "react";
import { RotateCcw, UploadCloud } from "lucide-react";
import type { AnalysisFailure } from "@sentinelai/shared";

import { AnalysisStateIndicator, type ClientAnalysisState } from "@/components/command-center/analysis-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"];

export interface UploadPanelProps {
  isDemoMode: boolean;
  hasActiveAnalysis: boolean;
  state: ClientAnalysisState;
  failure: AnalysisFailure | null;
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
 */
export function UploadPanel({
  isDemoMode,
  hasActiveAnalysis,
  state,
  failure,
  uploadErrorMessage,
  onFileSelected,
  onReset,
  className,
}: UploadPanelProps) {
  const [isDragOver, setIsDragOver] = React.useState(false);
  const [validationError, setValidationError] = React.useState<string | null>(null);
  const inputRef = React.useRef<HTMLInputElement | null>(null);

  const handleFile = (file: File) => {
    setValidationError(null);
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setValidationError("Unsupported file type. Upload a JPEG, PNG, or WEBP image.");
      return;
    }
    onFileSelected(file);
  };

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
          <div
            role="button"
            tabIndex={0}
            aria-label="Upload a satellite or disaster image for analysis"
            onClick={() => inputRef.current?.click()}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
            }}
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragOver(true);
            }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={(event) => {
              event.preventDefault();
              setIsDragOver(false);
              const file = event.dataTransfer.files[0];
              if (file) handleFile(file);
            }}
            className={`flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed p-6 text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
              isDragOver ? "border-sky-400 bg-sky-500/5" : "border-border hover:border-sky-500/50"
            }`}
          >
            <UploadCloud className="text-muted-foreground size-6" aria-hidden="true" />
            <p className="text-sm font-medium">Drop a satellite/disaster image, or click to browse</p>
            <p className="text-muted-foreground text-xs">JPEG, PNG, or WEBP</p>
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPTED_TYPES.join(",")}
              className="sr-only"
              aria-hidden="true"
              tabIndex={-1}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) handleFile(file);
                event.target.value = "";
              }}
            />
          </div>
        ) : (
          <AnalysisStateIndicator state={state} failure={failure} />
        )}

        {validationError && (
          <Alert variant="destructive">
            <AlertTitle>Invalid file</AlertTitle>
            <AlertDescription>{validationError}</AlertDescription>
          </Alert>
        )}

        {uploadErrorMessage && (
          <Alert variant="destructive">
            <AlertTitle>Upload failed</AlertTitle>
            <AlertDescription>{uploadErrorMessage}</AlertDescription>
          </Alert>
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

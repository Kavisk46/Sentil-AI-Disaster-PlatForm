"use client";

import * as React from "react";
import { AlertTriangle, ImageIcon, RotateCcw, UploadCloud } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ProvenanceBadge } from "@/components/ui/provenance-badge";
import { formatBytes } from "@/lib/format";
import { cn } from "@/lib/utils";

const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"];

interface FileMetadata {
  name: string;
  size: number;
  dimensions: { width: number; height: number } | null;
}

export interface UploadDropzoneProps {
  isUploading: boolean;
  /** 0..1 real byte progress from `xhr.upload.onprogress`, or `null` before
   * any progress event has fired (renders as indeterminate — never a
   * fabricated percentage). */
  uploadProgress: number | null;
  uploadErrorMessage: string | null;
  onFileSelected: (file: File) => void;
  /** "hero" is larger/looser for the landing page; "compact" matches the
   * dashboard's info-rail card sizing. Same behavior either way. */
  variant?: "compact" | "hero";
  className?: string;
}

/**
 * The shared drag-and-drop + validate + preview + progress + retry
 * uploader used by both `landing-upload.tsx` (hero) and `upload-panel.tsx`
 * (dashboard, compact). Purely presentational/local-state — data-fetching
 * still lives entirely in `command-center.tsx`/`landing-page.tsx` (the
 * hook owners), passed down as `isUploading`/`uploadProgress`/
 * `uploadErrorMessage` props, per `docs/architecture/frontend.md`.
 */
export function UploadDropzone({
  isUploading,
  uploadProgress,
  uploadErrorMessage,
  onFileSelected,
  variant = "compact",
  className,
}: UploadDropzoneProps) {
  const [isDragOver, setIsDragOver] = React.useState(false);
  const [validationError, setValidationError] = React.useState<string | null>(null);
  const [selectedFile, setSelectedFile] = React.useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = React.useState<string | null>(null);
  const [dimensions, setDimensions] = React.useState<{ width: number; height: number } | null>(null);
  const inputRef = React.useRef<HTMLInputElement | null>(null);

  // Revoke the previous object URL whenever it's replaced or this
  // component unmounts, so we don't leak blob URLs across uploads.
  React.useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const handleFile = React.useCallback(
    (file: File) => {
      setValidationError(null);
      if (!ACCEPTED_TYPES.includes(file.type)) {
        setValidationError("Unsupported file type. Upload a JPEG, PNG, or WEBP image.");
        return;
      }
      setPreviewUrl((current) => {
        if (current) URL.revokeObjectURL(current);
        return URL.createObjectURL(file);
      });
      setDimensions(null);
      setSelectedFile(file);
      onFileSelected(file);
    },
    [onFileSelected],
  );

  const metadata: FileMetadata | null = selectedFile
    ? { name: selectedFile.name, size: selectedFile.size, dimensions }
    : null;

  const isHero = variant === "hero";

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload a satellite or disaster image for analysis"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            inputRef.current?.click();
          }
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
        className={cn(
          "flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          isHero ? "p-10 sm:p-14" : "p-6",
          isDragOver ? "border-sky-400 bg-sky-500/5" : "border-border hover:border-sky-500/50",
        )}
      >
        <UploadCloud className={cn("text-muted-foreground", isHero ? "size-9" : "size-6")} aria-hidden="true" />
        <p className={cn("font-medium", isHero ? "text-base" : "text-sm")}>
          Drop a satellite/disaster image, or click to browse
        </p>
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

      {metadata && previewUrl && (
        <div className="flex gap-3 rounded-lg border border-border/60 p-2.5">
          {/* eslint-disable-next-line @next/next/no-img-element -- a
              locally-created blob: URL, not an optimizable remote image */}
          <img
            src={previewUrl}
            alt={`Preview of ${metadata.name}`}
            onLoad={(event) => {
              const img = event.currentTarget;
              setDimensions({ width: img.naturalWidth, height: img.naturalHeight });
            }}
            className="size-16 shrink-0 rounded-md border border-border/60 object-cover"
          />
          <div className="flex min-w-0 flex-1 flex-col justify-center gap-0.5 text-xs">
            <div className="flex items-center gap-1.5">
              <ImageIcon className="text-muted-foreground size-3.5 shrink-0" aria-hidden="true" />
              <span className="truncate font-medium">{metadata.name}</span>
              <ProvenanceBadge category="observed" className="ml-auto shrink-0" />
            </div>
            <p className="text-muted-foreground">
              {formatBytes(metadata.size)}
              {metadata.dimensions ? ` · ${metadata.dimensions.width}×${metadata.dimensions.height}px` : ""}
            </p>
          </div>
        </div>
      )}

      {isUploading && (
        <div className="flex flex-col gap-1.5">
          <Progress value={uploadProgress} indeterminate={uploadProgress === null} />
          <p className="text-muted-foreground text-xs">
            {uploadProgress === null
              ? "Uploading..."
              : `Uploading — ${Math.round(uploadProgress * 100)}%`}
          </p>
        </div>
      )}

      {validationError && (
        <Alert variant="destructive">
          <AlertTitle>Invalid file</AlertTitle>
          <AlertDescription>{validationError}</AlertDescription>
        </Alert>
      )}

      {uploadErrorMessage && (
        <Alert variant="destructive">
          <AlertTriangle className="size-4" />
          <AlertTitle>Upload failed</AlertTitle>
          <AlertDescription className="flex flex-col gap-2">
            {uploadErrorMessage}
            {selectedFile && (
              <Button
                variant="outline"
                size="sm"
                className="w-fit"
                onClick={() => handleFile(selectedFile)}
              >
                <RotateCcw className="size-3.5" />
                Retry
              </Button>
            )}
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}

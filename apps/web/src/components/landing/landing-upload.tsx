import { UploadDropzone, type UploadDropzoneProps } from "@/components/command-center/upload-dropzone";
import { cn } from "@/lib/utils";

export type LandingUploadProps = Omit<UploadDropzoneProps, "variant" | "className"> & {
  className?: string;
};

/**
 * Hero-scaled chrome around the shared `UploadDropzone` (see
 * `upload-dropzone.tsx`) for the landing page — same behavior as the
 * dashboard's upload panel, just larger and without the surrounding
 * `Card`/`CardHeader` rail chrome.
 */
export function LandingUpload(props: LandingUploadProps) {
  return (
    <div className={cn("glass-panel-elevated w-full max-w-xl rounded-xl p-5 sm:p-6", props.className)}>
      <UploadDropzone {...props} variant="hero" />
    </div>
  );
}

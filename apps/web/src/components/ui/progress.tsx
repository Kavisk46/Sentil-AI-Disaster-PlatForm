import { cn } from "@/lib/utils";

export interface ProgressProps {
  /** 0..1. Ignored (and treated as indeterminate) when `indeterminate` is true. */
  value?: number | null;
  /** True when no real fraction is known yet — renders a pulse, not a fake percentage. */
  indeterminate?: boolean;
  className?: string;
}

/**
 * A real, honest progress bar — `aria-valuenow` is only ever set from a
 * genuine caller-supplied fraction (see `lib/api-client.ts::apiUpload`'s
 * `onProgress`), never a guessed/animated number. `indeterminate` renders a
 * motion-safe pulse instead of a fabricated value. See
 * `docs/architecture/frontend.md`, "Upload progress".
 */
export function Progress({ value, indeterminate, className }: ProgressProps) {
  const pct = !indeterminate && value != null ? Math.round(Math.min(1, Math.max(0, value)) * 100) : null;

  return (
    <div
      data-slot="progress"
      role="progressbar"
      aria-label="Upload progress"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct ?? undefined}
      className={cn("bg-muted relative h-1.5 w-full overflow-hidden rounded-full", className)}
    >
      <div
        className={cn(
          "bg-primary h-full rounded-full motion-safe:transition-[width] motion-safe:duration-300",
          pct === null && "motion-safe:animate-pulse w-2/5",
        )}
        style={pct !== null ? { width: `${pct}%` } : undefined}
      />
    </div>
  );
}

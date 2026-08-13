import { cn } from "@/lib/utils";

/** A purposeful loading placeholder — sized/shaped like the content it
 * stands in for, never a fake progress percentage (see
 * `docs/architecture/frontend.md`, "Loading states"). Respects
 * `prefers-reduced-motion` via Tailwind's `motion-safe:` variant, so the
 * pulse only animates when the user hasn't asked to reduce motion. */
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("motion-safe:animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  );
}

export { Skeleton };

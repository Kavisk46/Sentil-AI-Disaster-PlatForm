"use client";

import { useIncidentStore } from "@/store/incident-store";

/**
 * A real, semantic checkbox styled as a switch — not a `<div onClick>` —
 * so it's keyboard-operable and announced correctly by screen readers
 * (`role="switch"` via `type="checkbox"` + `aria-checked` is implicit for
 * native checkboxes, but we set it explicitly for clarity).
 */
export function DemoModeToggle() {
  const isDemoMode = useIncidentStore((state) => state.isDemoMode);
  const setDemoMode = useIncidentStore((state) => state.setDemoMode);

  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm">
      <span className="text-muted-foreground">Demo mode</span>
      <input
        type="checkbox"
        role="switch"
        aria-checked={isDemoMode}
        aria-label="Toggle demo mode"
        checked={isDemoMode}
        onChange={(event) => setDemoMode(event.target.checked)}
        className="peer sr-only"
      />
      <span
        aria-hidden="true"
        className="relative h-5 w-9 rounded-full bg-muted transition-colors peer-checked:bg-amber-500/70 peer-focus-visible:ring-2 peer-focus-visible:ring-ring after:absolute after:top-0.5 after:left-0.5 after:size-4 after:rounded-full after:bg-background after:transition-transform peer-checked:after:translate-x-4"
      />
    </label>
  );
}

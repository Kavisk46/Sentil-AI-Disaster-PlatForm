import { ThemeToggle } from "@/components/theme-toggle";

/**
 * Minimal chrome for the landing/upload page — logo and theme toggle
 * only. Deliberately NOT `TopBar`: the demo-mode switch and live API
 * status belong to the analysis workspace (`/dashboard`), not a marketing
 * page with no active analysis to report on.
 */
export function LandingTopBar() {
  return (
    <header className="glass-panel flex h-14 shrink-0 items-center justify-between px-4">
      <span className="text-sm font-semibold tracking-wide">SentinelAI</span>
      <ThemeToggle />
    </header>
  );
}

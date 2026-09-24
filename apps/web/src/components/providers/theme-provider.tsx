"use client";

import * as React from "react";
import { ThemeProvider as NextThemesProvider } from "next-themes";

/**
 * Wraps next-themes so dark/light mode is resolved on the client and
 * persisted, without us re-implementing theme storage/detection.
 * `attribute="class"` matches the `.dark` selector convention Tailwind and
 * shadcn/ui components expect.
 *
 * `defaultTheme="dark"`: a disaster-response command center reads as an
 * operational instrument primarily in its dark, glass/cinematic form —
 * the same reasoning mission-control-style products (Palantir Foundry,
 * Vercel's own dashboard) default to dark. `enableSystem` is kept off so
 * a first-time visitor with a light-mode OS preference still sees the
 * intended product identity; the toggle in the top bar remains a fully
 * persisted, one-click override either way.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider attribute="class" defaultTheme="dark" disableTransitionOnChange>
      {children}
    </NextThemesProvider>
  );
}

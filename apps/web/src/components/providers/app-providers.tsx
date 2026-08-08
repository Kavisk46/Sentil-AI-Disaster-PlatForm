import * as React from "react";

import { QueryProvider } from "@/components/providers/query-provider";
import { ThemeProvider } from "@/components/providers/theme-provider";

/**
 * Single composition point for every client-side provider the app needs.
 * `layout.tsx` renders one `<AppProviders>` rather than a growing stack of
 * nested provider components, so adding a new provider later is a one-line
 * change here instead of a `layout.tsx` edit.
 */
export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <QueryProvider>{children}</QueryProvider>
    </ThemeProvider>
  );
}

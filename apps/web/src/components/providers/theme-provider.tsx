"use client";

import * as React from "react";
import { ThemeProvider as NextThemesProvider } from "next-themes";

/**
 * Wraps next-themes so dark/light mode is resolved on the client and
 * persisted, without us re-implementing theme storage/detection.
 * `attribute="class"` matches the `.dark` selector convention Tailwind and
 * shadcn/ui components expect.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      {children}
    </NextThemesProvider>
  );
}

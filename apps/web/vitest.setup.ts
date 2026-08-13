import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import "@testing-library/jest-dom/vitest";

// React Testing Library's automatic cleanup only self-registers when it
// detects Jest-style global test hooks; this project intentionally doesn't
// enable Vitest's `globals: true` (explicit imports everywhere else), so
// cleanup is wired up explicitly here instead — otherwise each test's
// rendered DOM would leak into the next test in the same file.
afterEach(() => {
  cleanup();
});

// jsdom has no real layout/media-query engine, so `window.matchMedia`
// doesn't exist — several components (e.g. `command-map.tsx`,
// `theme-toggle.tsx`'s underlying `next-themes`) call it. This stub always
// reports "no preference", which is the safe default for tests that don't
// specifically exercise `prefers-reduced-motion` behavior.
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

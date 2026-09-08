import { render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LandingHeroMap } from "@/components/landing/landing-hero-map";

/**
 * A minimal fake standing in for the real `maplibre-gl` module. Unlike
 * `command-center.test.tsx` (which mocks out the whole
 * `command-map-loader` because it only cares about data-flow, not map
 * internals), this test needs `command-map.tsx`'s *own* render logic to
 * actually run, since it's asserting on the `decorative` prop's effect on
 * that component's JSX — so only the WebGL-touching library underneath it
 * is faked, not the component itself.
 */
vi.mock("maplibre-gl", () => {
  class FakeMap {
    on() {}
    once() {}
    addControl() {}
    getBearing() {
      return 0;
    }
    setBearing() {}
    resize() {}
    remove() {}
  }
  return {
    Map: FakeMap,
    NavigationControl: class {},
    ScaleControl: class {},
  };
});

describe("LandingHeroMap", () => {
  it("is hidden from assistive tech and renders no feature/route text summary — it's decorative, not a data view", async () => {
    const { container } = render(<LandingHeroMap />);

    // `CommandMapLoader` is `next/dynamic(..., { ssr: false })`, which
    // resolves asynchronously even in a test — wait for the real
    // `CommandMap` (not its loading skeleton) to mount before asserting.
    // A generous explicit timeout: Testing Library's 1000ms default is too
    // tight for a dynamic import to resolve in this project's test
    // environment (module transform/import overhead here routinely runs
    // into several seconds — see `testTimeout: 15_000` in
    // `vitest.config.ts`), which isn't specific to this one test.
    await waitFor(() => expect(container.querySelector("[aria-hidden]")).not.toBeNull(), {
      timeout: 10_000,
    });

    expect(container.querySelector("[aria-hidden='true']")).toBeInTheDocument();
    expect(container.querySelector('[role="application"]')).not.toBeInTheDocument();
    expect(container.querySelector('[aria-live="polite"]')).not.toBeInTheDocument();
  });
});

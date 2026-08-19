import { CommandMapLoader } from "@/components/map/command-map-loader";

/**
 * The landing hero visual: the same MapLibre technology the dashboard
 * uses (see `docs/architecture/frontend.md`, "Map technology" — the
 * project's own "genuine 3D camera movement" is this tilted/rotating
 * WebGL scene, not a decorative shape), reused rather than forked, staged
 * decoratively via `command-map.tsx`'s additive `initialView`/
 * `interactive`/`autoRotate`/`decorative` props. No damage/route data is
 * passed, and the starting camera is centered on open ocean — the same
 * "never a real place" convention `lib/demo/demo-data.ts` uses for its
 * fictional `ORIGIN`, applied here for the same reason: nothing about
 * this page should read as surveillance of, or a claim about, any real
 * location.
 */
const OPEN_OCEAN_VIEW = { center: [-30, 5] as [number, number], zoom: 3.2, pitch: 55, bearing: -20 };

export function LandingHeroMap() {
  return (
    <CommandMapLoader
      damage={null}
      distanceOnlyRoute={null}
      riskAwareRoute={null}
      routeStart={null}
      routeDestination={null}
      initialView={OPEN_OCEAN_VIEW}
      interactive={false}
      autoRotate
      decorative
      className="size-full"
    />
  );
}

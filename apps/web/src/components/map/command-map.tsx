"use client";

import * as React from "react";
import type * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type {
  DamageFeatureCollection,
  GeographicCoordinate,
  RouteResult,
} from "@sentinelai/shared";

import { routeCollection, routeToLineFeature, routeToRiskSegments } from "@/lib/geo";
import { DAMAGE_CLASS_STYLE, DAMAGE_CLASS_WEIGHT, RISK_LEVEL_STYLE, ROUTE_MODE_STYLE } from "@/lib/risk-colors";

/**
 * The default basemap style: MapLibre's own free, no-API-key "demotiles"
 * style (maintained by the MapLibre project for exactly this purpose —
 * testing/demos with no account or token required). Production
 * deployments that want richer cartography can point
 * `NEXT_PUBLIC_MAP_STYLE_URL` at a real tile provider without a code
 * change — see `docs/architecture/frontend.md`, "Map technology".
 */
const DEFAULT_STYLE_URL =
  process.env.NEXT_PUBLIC_MAP_STYLE_URL ?? "https://demotiles.maplibre.org/style.json";

const EMPTY_FEATURE_COLLECTION = { type: "FeatureCollection" as const, features: [] };

export interface CommandMapInitialView {
  center: [number, number];
  zoom: number;
  pitch?: number;
  bearing?: number;
}

export interface CommandMapProps {
  damage: DamageFeatureCollection | null;
  distanceOnlyRoute: RouteResult | null;
  riskAwareRoute: RouteResult | null;
  routeStart: GeographicCoordinate | null;
  routeDestination: GeographicCoordinate | null;
  /** Fires when the user clicks the map, for picking route start/destination. */
  onMapClick?: (point: GeographicCoordinate) => void;
  className?: string;
  /**
   * Starting camera position. Defaults to `[0, 0]`/zoom 1.5/pitch 45°
   * (the dashboard's existing behavior, unchanged) — only the landing
   * hero passes a specific view.
   */
  initialView?: CommandMapInitialView;
  /**
   * When `false`, disables every built-in mouse/touch/keyboard handler
   * (drag, scroll-zoom, etc.) via MapLibre's own `interactive` map option,
   * skips `NavigationControl`/`ScaleControl`, and never wires
   * `onMapClick`. Used by the decorative landing hero, which is not meant
   * to be operated. Default `true` (today's dashboard behavior).
   */
  interactive?: boolean;
  /**
   * Slow, continuous bearing drift for a decorative hero shot — skipped
   * entirely under `prefers-reduced-motion`, same convention as the
   * existing pitch/fitBounds motion checks below. Default `false`.
   */
  autoRotate?: boolean;
  /**
   * Marks the map as pure decoration for assistive tech (`aria-hidden`)
   * and skips the `aria-live` feature-count summary, which would be
   * meaningless on a marketing page with no real analysis loaded. Default
   * `false` (today's dashboard behavior, which needs the real summary).
   */
  decorative?: boolean;
}

const SOURCE_IDS = {
  damage: "sentinelai-damage",
  distanceOnlyRoute: "sentinelai-route-distance-only",
  riskAwareRoute: "sentinelai-route-risk-aware",
  riskSegments: "sentinelai-route-risk-segments",
  points: "sentinelai-route-points",
} as const;

function pointsFeatureCollection(
  start: GeographicCoordinate | null,
  destination: GeographicCoordinate | null,
) {
  const features = [];
  if (start) {
    features.push({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [start.longitude, start.latitude] },
      properties: { role: "start" },
    });
  }
  if (destination) {
    features.push({
      type: "Feature" as const,
      geometry: {
        type: "Point" as const,
        coordinates: [destination.longitude, destination.latitude],
      },
      properties: { role: "destination" },
    });
  }
  return { type: "FeatureCollection" as const, features };
}

/**
 * Renders SentinelAI's damage/road-risk/route layers on a MapLibre GL JS
 * scene with camera pitch/bearing enabled (real WebGL tilt and rotation,
 * not a decorative 3D shape — see `docs/architecture/frontend.md`, "Map
 * technology"). Loads `maplibre-gl` dynamically inside `useEffect` so this
 * module never touches `window` during any server render pass, even if a
 * caller forgets the `next/dynamic(..., { ssr: false })` wrapper this
 * component is meant to be used behind (see `command-map-loader.tsx`).
 */
export function CommandMap({
  damage,
  distanceOnlyRoute,
  riskAwareRoute,
  routeStart,
  routeDestination,
  onMapClick,
  className,
  initialView,
  interactive = true,
  autoRotate = false,
  decorative = false,
}: CommandMapProps) {
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const mapRef = React.useRef<maplibregl.Map | null>(null);
  const onMapClickRef = React.useRef(onMapClick);
  onMapClickRef.current = onMapClick;
  // Read once at mount, like `onMapClickRef` — a given `CommandMap` usage
  // (dashboard vs. landing hero) doesn't change these mid-life.
  const initialViewRef = React.useRef(initialView);
  const interactiveRef = React.useRef(interactive);
  const autoRotateRef = React.useRef(autoRotate);
  const [isReady, setIsReady] = React.useState(false);

  // Mount: create the map exactly once. Deliberately not re-created on
  // prop changes — layer *content* updates happen in the effects below via
  // `setData`, which is far cheaper than tearing down and recreating the
  // whole WebGL context on every fetch.
  React.useEffect(() => {
    if (typeof window === "undefined" || !containerRef.current) return;

    let cancelled = false;
    let map: maplibregl.Map | null = null;
    let rotateFrameId: number | null = null;

    void import("maplibre-gl").then((maplibregl) => {
      if (cancelled || !containerRef.current) return;

      const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const view = initialViewRef.current;
      const isInteractive = interactiveRef.current;

      map = new maplibregl.Map({
        container: containerRef.current,
        style: DEFAULT_STYLE_URL,
        center: view?.center ?? [0, 0],
        zoom: view?.zoom ?? 1.5,
        pitch: prefersReducedMotion ? 0 : (view?.pitch ?? 45),
        maxPitch: 70,
        bearing: view?.bearing ?? 0,
        attributionControl: { compact: true },
        interactive: isInteractive,
      });

      if (isInteractive) {
        map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
        map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");

        map.on("click", (event) => {
          onMapClickRef.current?.({
            latitude: event.lngLat.lat,
            longitude: event.lngLat.lng,
          });
        });
      }

      if (autoRotateRef.current && !prefersReducedMotion) {
        const spin = () => {
          map?.setBearing((map.getBearing() + 0.02) % 360);
          rotateFrameId = requestAnimationFrame(spin);
        };
        rotateFrameId = requestAnimationFrame(spin);
      }

      map.on("load", () => {
        if (cancelled) return;

        map!.addSource(SOURCE_IDS.damage, { type: "geojson", data: EMPTY_FEATURE_COLLECTION });
        map!.addLayer({
          id: `${SOURCE_IDS.damage}-polygons`,
          type: "fill",
          source: SOURCE_IDS.damage,
          filter: ["==", ["geometry-type"], "Polygon"],
          paint: {
            "fill-color": [
              "match",
              ["get", "damage_class"],
              "no_damage",
              DAMAGE_CLASS_STYLE.no_damage.hex,
              "minor",
              DAMAGE_CLASS_STYLE.minor.hex,
              "major",
              DAMAGE_CLASS_STYLE.major.hex,
              "destroyed",
              DAMAGE_CLASS_STYLE.destroyed.hex,
              DAMAGE_CLASS_STYLE.no_damage.hex,
            ],
            "fill-opacity": 0.45,
          },
        });
        map!.addLayer({
          id: `${SOURCE_IDS.damage}-points`,
          type: "circle",
          source: SOURCE_IDS.damage,
          filter: ["==", ["geometry-type"], "Point"],
          paint: {
            "circle-color": [
              "match",
              ["get", "damage_class"],
              "no_damage",
              DAMAGE_CLASS_STYLE.no_damage.hex,
              "minor",
              DAMAGE_CLASS_STYLE.minor.hex,
              "major",
              DAMAGE_CLASS_STYLE.major.hex,
              "destroyed",
              DAMAGE_CLASS_STYLE.destroyed.hex,
              DAMAGE_CLASS_STYLE.no_damage.hex,
            ],
            "circle-radius": [
              "match",
              ["get", "damage_class"],
              "no_damage",
              4 + DAMAGE_CLASS_WEIGHT.no_damage,
              "minor",
              4 + DAMAGE_CLASS_WEIGHT.minor,
              "major",
              4 + DAMAGE_CLASS_WEIGHT.major,
              "destroyed",
              4 + DAMAGE_CLASS_WEIGHT.destroyed,
              4,
            ],
            "circle-stroke-width": 1.5,
            "circle-stroke-color": "#0f172a",
          },
        });

        map!.addSource(SOURCE_IDS.distanceOnlyRoute, {
          type: "geojson",
          data: EMPTY_FEATURE_COLLECTION,
        });
        map!.addLayer({
          id: SOURCE_IDS.distanceOnlyRoute,
          type: "line",
          source: SOURCE_IDS.distanceOnlyRoute,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": ROUTE_MODE_STYLE.distance_only.hex,
            "line-width": 2,
            "line-dasharray": [1.5, 1.5],
            "line-opacity": 0.85,
          },
        });

        // Risk-graded segments render *underneath* the bold risk-aware
        // line as a colored halo, so the selected route keeps strong
        // visual emphasis (per the milestone's own requirement) while
        // still showing per-segment risk.
        map!.addSource(SOURCE_IDS.riskSegments, { type: "geojson", data: EMPTY_FEATURE_COLLECTION });
        map!.addLayer({
          id: SOURCE_IDS.riskSegments,
          type: "line",
          source: SOURCE_IDS.riskSegments,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": [
              "match",
              ["get", "riskLevel"],
              "low",
              RISK_LEVEL_STYLE.low.hex,
              "moderate",
              RISK_LEVEL_STYLE.moderate.hex,
              "high",
              RISK_LEVEL_STYLE.high.hex,
              "critical",
              RISK_LEVEL_STYLE.critical.hex,
              "#64748b",
            ],
            "line-width": 9,
            "line-opacity": 0.35,
          },
        });

        map!.addSource(SOURCE_IDS.riskAwareRoute, { type: "geojson", data: EMPTY_FEATURE_COLLECTION });
        map!.addLayer({
          id: SOURCE_IDS.riskAwareRoute,
          type: "line",
          source: SOURCE_IDS.riskAwareRoute,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": ROUTE_MODE_STYLE.risk_aware.hex,
            "line-width": 4.5,
          },
        });

        map!.addSource(SOURCE_IDS.points, { type: "geojson", data: EMPTY_FEATURE_COLLECTION });
        map!.addLayer({
          id: SOURCE_IDS.points,
          type: "circle",
          source: SOURCE_IDS.points,
          paint: {
            "circle-radius": 7,
            "circle-color": ["match", ["get", "role"], "start", "#22c55e", "destination", "#ef4444", "#94a3b8"],
            "circle-stroke-width": 2,
            "circle-stroke-color": "#0f172a",
          },
        });

        setIsReady(true);
      });

      mapRef.current = map;
    });

    return () => {
      cancelled = true;
      if (rotateFrameId !== null) cancelAnimationFrame(rotateFrameId);
      map?.remove();
      mapRef.current = null;
      setIsReady(false);
    };
    // Intentionally mount-only — see the effect comment above.
  }, []);

  // Resize the WebGL canvas whenever its container changes size (flex
  // layouts don't otherwise notify MapLibre of that).
  React.useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver(() => mapRef.current?.resize());
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  React.useEffect(() => {
    if (!isReady) return;
    const source = mapRef.current?.getSource(SOURCE_IDS.damage) as
      | maplibregl.GeoJSONSource
      | undefined;
    source?.setData(damage ?? EMPTY_FEATURE_COLLECTION);
  }, [damage, isReady]);

  React.useEffect(() => {
    if (!isReady) return;
    const distanceFeature = distanceOnlyRoute ? routeToLineFeature(distanceOnlyRoute) : null;
    const source = mapRef.current?.getSource(SOURCE_IDS.distanceOnlyRoute) as
      | maplibregl.GeoJSONSource
      | undefined;
    source?.setData(routeCollection(distanceFeature ? [distanceFeature] : []));
  }, [distanceOnlyRoute, isReady]);

  React.useEffect(() => {
    if (!isReady) return;
    const riskFeature = riskAwareRoute ? routeToLineFeature(riskAwareRoute) : null;
    const riskSegments = riskAwareRoute ? routeToRiskSegments(riskAwareRoute) : [];

    const routeSource = mapRef.current?.getSource(SOURCE_IDS.riskAwareRoute) as
      | maplibregl.GeoJSONSource
      | undefined;
    routeSource?.setData(routeCollection(riskFeature ? [riskFeature] : []));

    const segmentSource = mapRef.current?.getSource(SOURCE_IDS.riskSegments) as
      | maplibregl.GeoJSONSource
      | undefined;
    segmentSource?.setData(routeCollection(riskSegments));
  }, [riskAwareRoute, isReady]);

  React.useEffect(() => {
    if (!isReady) return;
    const source = mapRef.current?.getSource(SOURCE_IDS.points) as
      | maplibregl.GeoJSONSource
      | undefined;
    source?.setData(pointsFeatureCollection(routeStart, routeDestination));
  }, [routeStart, routeDestination, isReady]);

  // Fit the viewport to whatever data is actually available, once per
  // dataset change — never a fabricated/default "interesting" location.
  React.useEffect(() => {
    if (!isReady || !mapRef.current) return;
    const map = mapRef.current;
    const bounds: [number, number][] = [];

    for (const feature of damage?.features ?? []) {
      if (feature.geometry.type === "Point") bounds.push(feature.geometry.coordinates);
      else if (feature.geometry.type === "Polygon") bounds.push(...feature.geometry.coordinates[0]!);
    }
    for (const route of [distanceOnlyRoute, riskAwareRoute]) {
      if (route?.found) bounds.push(...route.route_geometry);
    }

    if (bounds.length === 0) return;

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const lons = bounds.map((b) => b[0]);
    const lats = bounds.map((b) => b[1]);
    const sw: [number, number] = [Math.min(...lons), Math.min(...lats)];
    const ne: [number, number] = [Math.max(...lons), Math.max(...lats)];

    map.fitBounds([sw, ne], {
      padding: 64,
      maxZoom: 16,
      duration: prefersReducedMotion ? 0 : 800,
    });
  }, [damage, distanceOnlyRoute, riskAwareRoute, isReady]);

  return (
    <div className={className} aria-hidden={decorative || undefined}>
      <div
        ref={containerRef}
        role={decorative ? undefined : "application"}
        aria-label={
          decorative ? undefined : "Disaster command map: damage locations, road risk, and rescue routes"
        }
        className="size-full"
      />
      {/* MapLibre's WebGL canvas cannot itself be made screen-reader
          navigable — this text summary is the accessible equivalent of
          what the map shows, per the milestone's "screen-reader labels
          for important controls" requirement. See
          docs/architecture/frontend.md, "Accessibility decisions". Skipped
          entirely for `decorative` maps (the landing hero) — announcing
          "No damage data loaded" on a marketing page with no analysis
          would be meaningless, not accessible. */}
      {!decorative && (
        <p className="sr-only" aria-live="polite">
          {damage
            ? `${damage.features.length} damage feature(s) shown.`
            : "No damage data loaded."}{" "}
          {riskAwareRoute?.found ? "A risk-aware route is shown." : ""}{" "}
          {distanceOnlyRoute?.found ? "A distance-only baseline route is shown." : ""}
        </p>
      )}
    </div>
  );
}

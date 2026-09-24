"use client";

import * as React from "react";
import type * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Compass, Crosshair, Layers, Mountain, Route as RouteIcon } from "lucide-react";
import type {
  DamageFeatureCollection,
  GeographicCoordinate,
  Resource,
  RouteResult,
  SearchZone,
} from "@sentinelai/shared";

import { routeCollection, routeToRiskSegments } from "@/lib/geo";
import {
  DAMAGE_CLASS_STYLE,
  DAMAGE_CLASS_WEIGHT,
  RESOURCE_AVAILABILITY_STYLE,
  RISK_LEVEL_STYLE,
  ROUTE_MODE_STYLE,
  SEARCH_PRIORITY_STYLE,
} from "@/lib/risk-colors";

/**
 * Default basemap styles: CARTO's free, no-API-key vector styles (the
 * same ones MapLibre's own official examples use), one per theme so the
 * map reads as a coherent part of the cinematic dark command-center
 * chrome instead of a bright default vector map dropped onto a dark UI.
 * `NEXT_PUBLIC_MAP_STYLE_URL`, if set, overrides both themes — production
 * deployments that want a specific tile provider (or the previous
 * MapLibre "demotiles" default) can still point at one without a code
 * change. See `docs/architecture/frontend.md`, "Map technology".
 */
const DARK_STYLE_URL = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";
const LIGHT_STYLE_URL = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";

/**
 * F6.1: real global elevation data — Mapzen's public-domain "Terrarium"
 * terrain tiles, now hosted on the AWS Open Data Registry
 * (registry.opendata.aws/terrain-tiles), free and keyless, the same
 * dataset MapLibre's own terrain examples use. This is genuine measured
 * elevation, not a fabricated height field — the one legitimate way to
 * give the map real 3D depth without inventing geography. There is no
 * equivalent free, keyless source of real building-height data, so 3D
 * building extrusion is deliberately NOT implemented (see the "load"
 * handler below) rather than faked from an assumed story height.
 */
const TERRAIN_TILES_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
const TERRAIN_ATTRIBUTION =
  'Terrain: <a href="https://github.com/tilezen/joerd/blob/master/docs/data-sources.md" target="_blank" rel="noopener noreferrer">Mapzen Terrarium</a>';

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
  /**
   * F3 search-priority zones. Rendered only for zones whose
   * `geometry_crs` is genuinely `"EPSG:4326"` — an IMAGE-space (or any
   * other non-geographic) zone is silently skipped rather than plotted as
   * if it were real geography (see `docs/architecture/frontend.md`, "Map
   * layers"). `null` disables the layer entirely.
   */
  searchZones?: SearchZone[] | null;
  /**
   * The top search zone's best resource candidate's computed route
   * (`AnalysisCapabilityMatch.route`), rendered distinctly from the
   * route-comparison layers above — a recommendation, not a
   * user-selected comparison. `null`/not found renders nothing, never an
   * invented path.
   */
  recommendedRoute?: RouteResult | null;
  /**
   * F6.1: the highest-priority zone's id (matches `IntelligencePanel`'s
   * own `topSearchZoneId`) — the only zone that gets the pulsing
   * emphasis treatment, so "where should we look first" stays
   * unambiguous rather than every zone competing for attention.
   */
  topSearchZoneId?: string | null;
  /**
   * F6.1: the zone currently selected in `IntelligencePanel` — lifted to
   * `command-center.tsx` (see its own doc comment) so selecting a zone in
   * the panel visibly highlights it on the map, and vice versa via
   * `onSelectZone`. `null` means nothing is explicitly selected (the
   * panel falls back to the top zone on its own).
   */
  selectedZoneId?: string | null;
  /** Fires when the user clicks a plotted search zone on the map. */
  onSelectZone?: (zoneId: string) => void;
  /**
   * F6.1: resource markers. Real (F3) mode can only ever honestly supply
   * the single top capability-match candidate's location (derived from
   * its computed route's start point — see `command-center.tsx` — the F3
   * API has no resource-location field of its own); Demo mode supplies
   * the full `DEMO_RESOURCES` fixture. `null` disables the layer.
   */
  resources?: Resource[] | null;
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
  searchZones: "sentinelai-search-zones",
  recommendedRoute: "sentinelai-route-recommended",
  resources: "sentinelai-resources",
  terrainDem: "sentinelai-terrain-dem",
} as const;

/** Only ever plot a zone whose CRS is genuinely tagged geographic — never
 * treat IMAGE-space (or any other non-WGS84) coordinates as lon/lat, the
 * same safeguard `affected-area-panel.tsx` and `app.intelligence.analysis_adapter`
 * already apply. Only point geometries are supported today — F3 never
 * produces polygon search zones. */
function searchZonesFeatureCollection(zones: SearchZone[] | null) {
  const features = (zones ?? []).flatMap((zone) => {
    if (zone.geometry_crs !== "EPSG:4326" || zone.geometry.type !== "point") return [];
    return [
      {
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: zone.geometry.coordinates },
        properties: { priority_level: zone.priority_level, id: zone.id },
      },
    ];
  });
  return { type: "FeatureCollection" as const, features };
}

/** Same CRS safeguard as `searchZonesFeatureCollection` above — a
 * resource whose location isn't genuinely WGS84 is skipped, never
 * plotted. See `CommandMapProps.resources`'s doc comment for how real
 * vs. demo resource data differs. */
function resourcesFeatureCollection(resources: Resource[] | null) {
  const features = (resources ?? []).flatMap((resource) => {
    const location = resource.location;
    if (resource.location_crs !== "EPSG:4326" || !location || location.type !== "point") return [];
    return [
      {
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: location.coordinates },
        properties: {
          id: resource.id,
          availability: resource.availability,
          type: resource.type,
          is_simulated: resource.is_simulated,
        },
      },
    ];
  });
  return { type: "FeatureCollection" as const, features };
}

/**
 * F6.1: animates a real route's already-computed geometry being "drawn"
 * onto the map over ~700ms by progressively revealing more of its actual
 * coordinate list — never interpolated/invented points, purely a reveal
 * order over real data that already exists. Skips straight to the full
 * line under `prefers-reduced-motion`. Returns a cleanup function that
 * cancels the animation if the route changes again mid-reveal.
 */
function animateRouteReveal(
  source: maplibregl.GeoJSONSource | undefined,
  coordinates: [number, number][],
  prefersReducedMotion: boolean,
  mode: string,
): () => void {
  if (!source) return () => {};
  if (prefersReducedMotion || coordinates.length < 2) {
    source.setData(
      routeCollection([
        { type: "Feature", geometry: { type: "LineString", coordinates }, properties: { mode } },
      ]),
    );
    return () => {};
  }

  const durationMs = 700;
  const startedAt = performance.now();
  let frameId: number | null = null;

  const step = (now: number) => {
    const progress = Math.min(1, (now - startedAt) / durationMs);
    // Ease-out: fast start, gentle finish — reads as a deliberate
    // "route found" reveal rather than a linear wipe.
    const eased = 1 - (1 - progress) ** 3;
    const pointCount = Math.max(2, Math.round(eased * (coordinates.length - 1)) + 1);
    source.setData(
      routeCollection([
        {
          type: "Feature",
          geometry: { type: "LineString", coordinates: coordinates.slice(0, pointCount) },
          properties: { mode },
        },
      ]),
    );
    if (progress < 1) frameId = requestAnimationFrame(step);
  };
  frameId = requestAnimationFrame(step);

  return () => {
    if (frameId !== null) cancelAnimationFrame(frameId);
  };
}

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
  searchZones = null,
  recommendedRoute = null,
  topSearchZoneId = null,
  selectedZoneId = null,
  onSelectZone,
  resources = null,
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
  const onSelectZoneRef = React.useRef(onSelectZone);
  onSelectZoneRef.current = onSelectZone;
  // Read once at mount, like `onMapClickRef` — a given `CommandMap` usage
  // (dashboard vs. landing hero) doesn't change these mid-life.
  const initialViewRef = React.useRef(initialView);
  const interactiveRef = React.useRef(interactive);
  const autoRotateRef = React.useRef(autoRotate);
  const [isReady, setIsReady] = React.useState(false);
  // F6.1: whether the camera has already done its one-time cinematic
  // entrance for the currently loaded dataset — reset when the map
  // empties out again (e.g. the user clears the active analysis), so a
  // *new* analysis gets its own entrance rather than a jarring silent
  // jump. Not a ref: read only inside the bounds effect below, which
  // already re-runs on every relevant data change.
  const hasCinematicEnteredRef = React.useRef(false);
  const [is3DEnabled, setIs3DEnabled] = React.useState(true);
  const [hasFramedData, setHasFramedData] = React.useState(false);

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
      // Read the theme once at mount, the same way `prefersReducedMotion`
      // is read directly rather than via a hook — next-themes applies the
      // `.dark` class synchronously (a blocking inline script) before
      // hydration, so this is reliable even on first paint. A theme
      // toggled *after* the map has already loaded does not re-style the
      // basemap (documented limitation, not a bug — see
      // `docs/architecture/frontend.md`, "Map layers").
      const isDarkTheme = document.documentElement.classList.contains("dark");
      const styleUrl =
        process.env.NEXT_PUBLIC_MAP_STYLE_URL ?? (isDarkTheme ? DARK_STYLE_URL : LIGHT_STYLE_URL);

      map = new maplibregl.Map({
        container: containerRef.current,
        style: styleUrl,
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

        // F3: search zones — "high-priority search zone based on
        // available evidence," never a marker claiming a person is
        // located here (see SearchZone's own doc comment). A pulsing
        // halo under a solid core keeps critical zones visually
        // distinct without relying on color alone (WCAG 1.4.1) — the
        // priority_level is also available via the sr-only summary
        // below and every intelligence-panel.tsx badge.
        map!.addSource(SOURCE_IDS.searchZones, { type: "geojson", data: EMPTY_FEATURE_COLLECTION });
        map!.addLayer({
          id: `${SOURCE_IDS.searchZones}-halo`,
          type: "circle",
          source: SOURCE_IDS.searchZones,
          paint: {
            "circle-radius": 16,
            "circle-color": [
              "match",
              ["get", "priority_level"],
              "critical",
              SEARCH_PRIORITY_STYLE.critical.hex,
              "high",
              SEARCH_PRIORITY_STYLE.high.hex,
              "moderate",
              SEARCH_PRIORITY_STYLE.moderate.hex,
              SEARCH_PRIORITY_STYLE.low.hex,
            ],
            "circle-opacity": 0.2,
          },
        });
        map!.addLayer({
          id: SOURCE_IDS.searchZones,
          type: "circle",
          source: SOURCE_IDS.searchZones,
          paint: {
            "circle-radius": 7,
            "circle-color": [
              "match",
              ["get", "priority_level"],
              "critical",
              SEARCH_PRIORITY_STYLE.critical.hex,
              "high",
              SEARCH_PRIORITY_STYLE.high.hex,
              "moderate",
              SEARCH_PRIORITY_STYLE.moderate.hex,
              SEARCH_PRIORITY_STYLE.low.hex,
            ],
            "circle-stroke-width": 2,
            "circle-stroke-color": "#0f172a",
          },
        });

        // F3: the top-priority zone's best resource candidate's
        // computed route — a recommendation layer, styled distinctly
        // (magenta, wide dash) from the user-driven route-comparison
        // layers above so the two are never visually confused.
        map!.addSource(SOURCE_IDS.recommendedRoute, {
          type: "geojson",
          data: EMPTY_FEATURE_COLLECTION,
        });
        map!.addLayer({
          id: SOURCE_IDS.recommendedRoute,
          type: "line",
          source: SOURCE_IDS.recommendedRoute,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": "#d946ef",
            "line-width": 3.5,
            "line-dasharray": [3, 1.5],
            "line-opacity": 0.9,
          },
        });

        // F6.1: selected-zone emphasis — a stroke-only ring, filtered to
        // whichever zone id `selectedZoneId`/`onSelectZone` (see
        // `command-center.tsx`, the single hook/state owner) currently
        // names. Starts matching nothing (`["==", ["get", "id"], ""]`);
        // the effect below updates the filter as selection changes. A
        // *shape* difference (ring vs. filled dot), not just a color
        // change, so it doesn't depend on color alone.
        map!.addLayer({
          id: `${SOURCE_IDS.searchZones}-selected`,
          type: "circle",
          source: SOURCE_IDS.searchZones,
          filter: ["==", ["get", "id"], ""],
          paint: {
            "circle-radius": 13,
            "circle-color": "transparent",
            "circle-stroke-width": 2.5,
            "circle-stroke-color": "#ffffff",
          },
        });

        // F6.1: a restrained pulse on the single highest-priority zone
        // only (never every zone — see `CommandMapProps.topSearchZoneId`'s
        // doc comment) so "look here first" stays unambiguous. Skipped
        // under `prefers-reduced-motion`; the effect below drives the
        // animation via a bounded `setInterval` (cheap paint-property
        // updates, not a per-frame rAF loop — see "Performance" in
        // `docs/architecture/frontend.md`).
        map!.addLayer({
          id: `${SOURCE_IDS.searchZones}-pulse`,
          type: "circle",
          source: SOURCE_IDS.searchZones,
          filter: ["==", ["get", "id"], ""],
          paint: {
            "circle-radius": 16,
            "circle-color": "transparent",
            "circle-stroke-width": 2,
            "circle-stroke-color": [
              "match",
              ["get", "priority_level"],
              "critical",
              SEARCH_PRIORITY_STYLE.critical.hex,
              "high",
              SEARCH_PRIORITY_STYLE.high.hex,
              "moderate",
              SEARCH_PRIORITY_STYLE.moderate.hex,
              SEARCH_PRIORITY_STYLE.low.hex,
            ],
            "circle-stroke-opacity": 0.9,
          },
        });

        if (isInteractive) {
          map!.on("mouseenter", SOURCE_IDS.searchZones, () => {
            map!.getCanvas().style.cursor = "pointer";
          });
          map!.on("mouseleave", SOURCE_IDS.searchZones, () => {
            map!.getCanvas().style.cursor = "";
          });
          map!.on("click", SOURCE_IDS.searchZones, (event) => {
            const zoneId = event.features?.[0]?.properties?.id as string | undefined;
            if (zoneId) onSelectZoneRef.current?.(zoneId);
          });
        }

        // F6.1: resource markers — see `CommandMapProps.resources`'s doc
        // comment for the real-vs-demo data-honesty distinction. Shape
        // (diamond via rotated square is unavailable in plain circle
        // layers, so a distinct stroke width + a dedicated legend entry
        // carries the non-color signal instead) mirrors the
        // damage/search-zone convention of never relying on color alone.
        map!.addSource(SOURCE_IDS.resources, { type: "geojson", data: EMPTY_FEATURE_COLLECTION });
        map!.addLayer({
          id: SOURCE_IDS.resources,
          type: "circle",
          source: SOURCE_IDS.resources,
          paint: {
            "circle-radius": 6,
            "circle-color": [
              "match",
              ["get", "availability"],
              "available",
              RESOURCE_AVAILABILITY_STYLE.available.hex,
              "deployed",
              RESOURCE_AVAILABILITY_STYLE.deployed.hex,
              "unavailable",
              RESOURCE_AVAILABILITY_STYLE.unavailable.hex,
              RESOURCE_AVAILABILITY_STYLE.unknown.hex,
            ],
            "circle-stroke-width": 2.5,
            "circle-stroke-color": "#ffffff",
          },
        });

        // F6.1: real elevation data (see `TERRAIN_TILES_URL`'s doc
        // comment above — never fabricated). Inserted *before* the base
        // style's own first layer so hillshading sits underneath roads/
        // labels rather than washing them out; every SentinelAI data
        // layer above was already added after the base style's layers,
        // so it stays on top of the hillshade automatically.
        const baseLayers = map!.getStyle().layers;
        const firstBaseLayerId = baseLayers && baseLayers.length > 0 ? baseLayers[0]!.id : undefined;
        map!.addSource(SOURCE_IDS.terrainDem, {
          type: "raster-dem",
          tiles: [TERRAIN_TILES_URL],
          tileSize: 256,
          encoding: "terrarium",
          maxzoom: 15,
          attribution: TERRAIN_ATTRIBUTION,
        });
        map!.addLayer(
          {
            id: `${SOURCE_IDS.terrainDem}-hillshade`,
            type: "hillshade",
            source: SOURCE_IDS.terrainDem,
            paint: {
              "hillshade-shadow-color": "#05050a",
              "hillshade-highlight-color": isDarkTheme ? "#1e3a5f" : "#e2e8f0",
              "hillshade-accent-color": "#0f172a",
              "hillshade-exaggeration": 0.6,
            },
          },
          firstBaseLayerId,
        );
        // Real 3D terrain displacement, on by default (matches the
        // existing default pitch of 45°) — see the `is3DEnabled` state
        // and the map-controls toggle below for how a responder can turn
        // it back to a flat, precise top-down view.
        map!.setTerrain({ source: SOURCE_IDS.terrainDem, exaggeration: 1.3 });

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
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const source = mapRef.current?.getSource(SOURCE_IDS.distanceOnlyRoute) as
      | maplibregl.GeoJSONSource
      | undefined;
    if (!distanceOnlyRoute?.found) {
      source?.setData(EMPTY_FEATURE_COLLECTION);
      return;
    }
    return animateRouteReveal(
      source,
      distanceOnlyRoute.route_geometry,
      prefersReducedMotion,
      distanceOnlyRoute.routing_mode,
    );
  }, [distanceOnlyRoute, isReady]);

  React.useEffect(() => {
    if (!isReady) return;
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const routeSource = mapRef.current?.getSource(SOURCE_IDS.riskAwareRoute) as
      | maplibregl.GeoJSONSource
      | undefined;
    const segmentSource = mapRef.current?.getSource(SOURCE_IDS.riskSegments) as
      | maplibregl.GeoJSONSource
      | undefined;
    // The risk-graded halo underneath renders instantly, alongside the
    // animated reveal of the bold line on top — segments are a supporting
    // detail layer, not the primary "route found" cue this animation is for.
    segmentSource?.setData(
      routeCollection(riskAwareRoute?.found ? routeToRiskSegments(riskAwareRoute) : []),
    );
    if (!riskAwareRoute?.found) {
      routeSource?.setData(EMPTY_FEATURE_COLLECTION);
      return;
    }
    return animateRouteReveal(
      routeSource,
      riskAwareRoute.route_geometry,
      prefersReducedMotion,
      riskAwareRoute.routing_mode,
    );
  }, [riskAwareRoute, isReady]);

  React.useEffect(() => {
    if (!isReady) return;
    const source = mapRef.current?.getSource(SOURCE_IDS.points) as
      | maplibregl.GeoJSONSource
      | undefined;
    source?.setData(pointsFeatureCollection(routeStart, routeDestination));
  }, [routeStart, routeDestination, isReady]);

  React.useEffect(() => {
    if (!isReady) return;
    const source = mapRef.current?.getSource(SOURCE_IDS.searchZones) as
      | maplibregl.GeoJSONSource
      | undefined;
    source?.setData(searchZonesFeatureCollection(searchZones));
  }, [searchZones, isReady]);

  // F6.1: the selected zone's stroke-ring — filtered to match whichever
  // id is actually selected (falling back to the top zone, mirroring
  // `IntelligencePanel`'s own fallback so the map and panel always agree
  // on what "selected" means without either owning the other's state).
  React.useEffect(() => {
    if (!isReady || !mapRef.current) return;
    const map = mapRef.current;
    if (!map.getLayer(`${SOURCE_IDS.searchZones}-selected`)) return;
    const effectiveId = selectedZoneId ?? topSearchZoneId ?? "";
    map.setFilter(`${SOURCE_IDS.searchZones}-selected`, ["==", ["get", "id"], effectiveId]);
  }, [selectedZoneId, topSearchZoneId, isReady]);

  // F6.1: the top zone's restrained pulse — a bounded `setInterval` loop
  // (not continuous rAF) toggling the pulse ring's radius/opacity between
  // two states, cleared whenever the top zone changes or this component
  // unmounts. Entirely skipped under `prefers-reduced-motion`.
  React.useEffect(() => {
    if (!isReady || !mapRef.current || !topSearchZoneId) return;
    const map = mapRef.current;
    const layerId = `${SOURCE_IDS.searchZones}-pulse`;
    if (!map.getLayer(layerId)) return;
    map.setFilter(layerId, ["==", ["get", "id"], topSearchZoneId]);

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let expanded = false;
    const intervalId = window.setInterval(() => {
      expanded = !expanded;
      map.setPaintProperty(layerId, "circle-radius", expanded ? 22 : 16);
      map.setPaintProperty(layerId, "circle-stroke-opacity", expanded ? 0.15 : 0.9);
    }, 900);

    return () => {
      window.clearInterval(intervalId);
      if (map.getLayer(layerId)) {
        map.setFilter(layerId, ["==", ["get", "id"], ""]);
      }
    };
  }, [topSearchZoneId, isReady]);

  // F6.1: a slow, restrained opacity pulse on the recommended-route line
  // only (the single most action-oriented layer) — a bounded
  // `setInterval` toggling `line-opacity` between two always-valid
  // values, not a per-frame animation loop. (A literal "marching ants"
  // dash-offset effect was deliberately not used here: MapLibre's
  // `line-dasharray` has no separate offset property, and hand-rolling
  // one via shifting dash/gap pairs risks producing a transiently
  // negative — invalid — array; this achieves the same "this route is
  // live/active" cue without that risk.)
  React.useEffect(() => {
    if (!isReady || !mapRef.current || !recommendedRoute?.found) return;
    const map = mapRef.current;
    if (!map.getLayer(SOURCE_IDS.recommendedRoute)) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let dimmed = false;
    const intervalId = window.setInterval(() => {
      dimmed = !dimmed;
      map.setPaintProperty(SOURCE_IDS.recommendedRoute, "line-opacity", dimmed ? 0.55 : 0.9);
    }, 700);

    return () => {
      window.clearInterval(intervalId);
      if (map.getLayer(SOURCE_IDS.recommendedRoute)) {
        map.setPaintProperty(SOURCE_IDS.recommendedRoute, "line-opacity", 0.9);
      }
    };
  }, [recommendedRoute, isReady]);

  React.useEffect(() => {
    if (!isReady) return;
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const source = mapRef.current?.getSource(SOURCE_IDS.recommendedRoute) as
      | maplibregl.GeoJSONSource
      | undefined;
    if (!recommendedRoute?.found) {
      source?.setData(EMPTY_FEATURE_COLLECTION);
      return;
    }
    return animateRouteReveal(
      source,
      recommendedRoute.route_geometry,
      prefersReducedMotion,
      recommendedRoute.routing_mode,
    );
  }, [recommendedRoute, isReady]);

  React.useEffect(() => {
    if (!isReady) return;
    const source = mapRef.current?.getSource(SOURCE_IDS.resources) as
      | maplibregl.GeoJSONSource
      | undefined;
    source?.setData(resourcesFeatureCollection(resources));
  }, [resources, isReady]);

  // Fit the viewport to whatever data is actually available, once per
  // dataset change — never a fabricated/default "interesting" location.
  //
  // F6.1: the *first* time real bounds appear (idle/empty -> populated),
  // this does a cinematic `flyTo` — a deliberate pitch/bearing composition,
  // not just a plain `fitBounds` — then never repeats that entrance again
  // for the same dataset; every later update (a new layer arriving, a
  // route being added) just does the original gentle `fitBounds`,
  // preserving whatever pitch/bearing the user has since chosen manually
  // (see "Cinematic camera" in `docs/architecture/frontend.md` — the user
  // must retain manual control, so nothing re-flies the camera on top of
  // their own adjustments). Bounds disappearing again (analysis cleared)
  // resets the one-time flag so the *next* analysis gets its own entrance.
  React.useEffect(() => {
    if (!isReady || !mapRef.current) return;
    const map = mapRef.current;
    const bounds: [number, number][] = [];

    for (const feature of damage?.features ?? []) {
      if (feature.geometry.type === "Point") bounds.push(feature.geometry.coordinates);
      else if (feature.geometry.type === "Polygon") bounds.push(...feature.geometry.coordinates[0]!);
    }
    for (const route of [distanceOnlyRoute, riskAwareRoute, recommendedRoute]) {
      if (route?.found) bounds.push(...route.route_geometry);
    }
    for (const zone of searchZones ?? []) {
      if (zone.geometry_crs === "EPSG:4326" && zone.geometry.type === "point") {
        bounds.push(zone.geometry.coordinates);
      }
    }

    if (bounds.length === 0) {
      hasCinematicEnteredRef.current = false;
      setHasFramedData(false);
      return;
    }
    setHasFramedData(true);

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const lons = bounds.map((b) => b[0]);
    const lats = bounds.map((b) => b[1]);
    const sw: [number, number] = [Math.min(...lons), Math.min(...lats)];
    const ne: [number, number] = [Math.max(...lons), Math.max(...lats)];

    if (!hasCinematicEnteredRef.current) {
      hasCinematicEnteredRef.current = true;
      map.fitBounds([sw, ne], {
        padding: 96,
        maxZoom: 15,
        pitch: prefersReducedMotion ? 0 : 55,
        bearing: prefersReducedMotion ? 0 : 18,
        duration: prefersReducedMotion ? 0 : 2200,
        essential: true,
      });
      return;
    }

    map.fitBounds([sw, ne], {
      padding: 64,
      maxZoom: 16,
      duration: prefersReducedMotion ? 0 : 800,
    });
  }, [damage, distanceOnlyRoute, riskAwareRoute, recommendedRoute, searchZones, isReady]);

  // F6.1: imperative handlers for the map-controls stack below. Kept
  // inline (not a separate component) because every one of them needs
  // direct `mapRef` access, which only this component holds — extracting
  // them would mean prop-drilling the map instance out, more complex than
  // the handlers themselves for no real benefit. All respect
  // `prefers-reduced-motion` the same way every other camera move above
  // does.
  const reducedMotionDuration = (duration: number) =>
    window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : duration;

  const handleToggle3D = () => {
    const map = mapRef.current;
    if (!map) return;
    const next = !is3DEnabled;
    setIs3DEnabled(next);
    if (next) {
      map.setTerrain({ source: SOURCE_IDS.terrainDem, exaggeration: 1.3 });
      map.easeTo({ pitch: 55, duration: reducedMotionDuration(900) });
    } else {
      map.setTerrain(null);
      map.easeTo({ pitch: 0, duration: reducedMotionDuration(900) });
    }
  };

  const handleRecenterIncident = () => {
    const map = mapRef.current;
    if (!map) return;
    const bounds: [number, number][] = [];
    for (const feature of damage?.features ?? []) {
      if (feature.geometry.type === "Point") bounds.push(feature.geometry.coordinates);
      else if (feature.geometry.type === "Polygon") bounds.push(...feature.geometry.coordinates[0]!);
    }
    for (const route of [distanceOnlyRoute, riskAwareRoute, recommendedRoute]) {
      if (route?.found) bounds.push(...route.route_geometry);
    }
    for (const zone of searchZones ?? []) {
      if (zone.geometry_crs === "EPSG:4326" && zone.geometry.type === "point") {
        bounds.push(zone.geometry.coordinates);
      }
    }
    if (bounds.length === 0) return;
    const lons = bounds.map((b) => b[0]);
    const lats = bounds.map((b) => b[1]);
    map.fitBounds(
      [
        [Math.min(...lons), Math.min(...lats)],
        [Math.max(...lons), Math.max(...lats)],
      ],
      { padding: 64, maxZoom: 16, duration: reducedMotionDuration(800) },
    );
  };

  const handleLocateTopZone = () => {
    const map = mapRef.current;
    const zone = (searchZones ?? []).find((candidate) => candidate.id === topSearchZoneId);
    if (!map || !zone || zone.geometry_crs !== "EPSG:4326" || zone.geometry.type !== "point") return;
    map.flyTo({
      center: zone.geometry.coordinates,
      zoom: Math.max(map.getZoom(), 15),
      pitch: is3DEnabled ? 55 : 0,
      duration: reducedMotionDuration(1200),
      essential: true,
    });
  };

  const focusableRoute = riskAwareRoute?.found
    ? riskAwareRoute
    : distanceOnlyRoute?.found
      ? distanceOnlyRoute
      : recommendedRoute?.found
        ? recommendedRoute
        : null;

  const handleFocusRoute = () => {
    const map = mapRef.current;
    if (!map || !focusableRoute) return;
    const lons = focusableRoute.route_geometry.map((point) => point[0]);
    const lats = focusableRoute.route_geometry.map((point) => point[1]);
    map.fitBounds(
      [
        [Math.min(...lons), Math.min(...lats)],
        [Math.max(...lons), Math.max(...lats)],
      ],
      { padding: 80, maxZoom: 17, duration: reducedMotionDuration(900) },
    );
  };

  const showControls = interactive && !decorative;

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

      {/* F6.1: incident focus — a restrained radial highlight around the
          framed region, pure CSS over the map container (never tied to
          real screen coordinates of any geographic feature, so this
          cannot be misread as plotting anything — it is atmosphere, not
          data). Only shown once real bounds exist; never on the
          decorative landing hero, which has no "incident" to focus on. */}
      {!decorative && hasFramedData && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse 70% 60% at 50% 45%, transparent 45%, var(--sentinel-glow) 100%)",
          }}
        />
      )}

      {showControls && (
        <div
          role="group"
          aria-label="Map controls"
          className="glass-panel absolute top-3 left-3 z-10 flex flex-col gap-1 rounded-lg p-1"
        >
          <button
            type="button"
            title={is3DEnabled ? "Switch to flat 2D view" : "Switch to 3D terrain view"}
            aria-label={is3DEnabled ? "Switch to flat 2D view" : "Switch to 3D terrain view"}
            aria-pressed={is3DEnabled}
            onClick={handleToggle3D}
            className="hover:bg-accent hover:text-accent-foreground focus-visible:ring-ring inline-flex size-8 items-center justify-center rounded-md transition-colors focus-visible:ring-2 focus-visible:outline-none"
          >
            <Mountain className="size-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            title="Recenter on the current incident"
            aria-label="Recenter on the current incident"
            disabled={!hasFramedData}
            onClick={handleRecenterIncident}
            className="hover:bg-accent hover:text-accent-foreground focus-visible:ring-ring inline-flex size-8 items-center justify-center rounded-md transition-colors focus-visible:ring-2 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-40"
          >
            <Crosshair className="size-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            title="Locate the top-priority search zone"
            aria-label="Locate the top-priority search zone"
            disabled={!topSearchZoneId}
            onClick={handleLocateTopZone}
            className="hover:bg-accent hover:text-accent-foreground focus-visible:ring-ring inline-flex size-8 items-center justify-center rounded-md transition-colors focus-visible:ring-2 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-40"
          >
            <Layers className="size-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            title="Focus the current route"
            aria-label="Focus the current route"
            disabled={!focusableRoute}
            onClick={handleFocusRoute}
            className="hover:bg-accent hover:text-accent-foreground focus-visible:ring-ring inline-flex size-8 items-center justify-center rounded-md transition-colors focus-visible:ring-2 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-40"
          >
            <RouteIcon className="size-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            title="Reset north (bearing 0°)"
            aria-label="Reset north"
            onClick={() => mapRef.current?.easeTo({ bearing: 0, duration: reducedMotionDuration(500) })}
            className="hover:bg-accent hover:text-accent-foreground focus-visible:ring-ring inline-flex size-8 items-center justify-center rounded-md transition-colors focus-visible:ring-2 focus-visible:outline-none"
          >
            <Compass className="size-4" aria-hidden="true" />
          </button>
        </div>
      )}

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
          {distanceOnlyRoute?.found ? "A distance-only baseline route is shown." : ""}{" "}
          {searchZones && searchZones.length > 0
            ? `${searchZones.length} search priority zone(s) shown.`
            : ""}{" "}
          {recommendedRoute?.found ? "A recommended route to the top-priority zone is shown." : ""}{" "}
          {resources && resources.length > 0
            ? `${resources.length} resource(s) plotted.`
            : ""}{" "}
          {is3DEnabled ? "3D terrain elevation is enabled." : "Flat 2D view is enabled."}
        </p>
      )}
    </div>
  );
}

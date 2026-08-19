import type {
  DamageFeatureCollection,
  GeoJsonFeature,
  GeoJsonFeatureCollection,
  GeoJsonLineString,
  GeoJsonPosition,
  RiskLevel,
  RouteComparison,
  RouteResult,
} from "@sentinelai/shared";

/** Properties MapLibre reads to style one route line. */
export interface RouteLineProperties {
  mode: RouteResult["routing_mode"];
}

/**
 * The full route as a single `LineString` feature, for the "whole route"
 * emphasis layer (bold for `risk_aware`, thin/dashed for `distance_only` —
 * see `components/map/command-map.tsx`). `null` when the route wasn't
 * found or has fewer than 2 points — a `LineString` needs at least 2
 * positions, and a trivial start==destination route only has 1 (the same
 * rule the backend's own `route_to_feature()` applies).
 */
export function routeToLineFeature(
  route: RouteResult,
): GeoJsonFeature<GeoJsonLineString, RouteLineProperties> | null {
  if (!route.found || route.route_geometry.length < 2) return null;
  return {
    type: "Feature",
    geometry: { type: "LineString", coordinates: route.route_geometry },
    properties: { mode: route.routing_mode },
  };
}

/** Per-edge risk level, for the risk-graded segment layer. */
export interface RouteRiskSegmentProperties {
  riskLevel: RiskLevel | "unknown";
  edgeIndex: number;
}

/**
 * Splits a route into one `LineString` feature per traversed edge, each
 * carrying that edge's real `risk_level` — real backend geometry
 * (`route_geometry`) paired with real backend risk data
 * (`edge_sequence[i].risk_level`), not an invented gradient. This is how
 * road risk is actually visualized *on the map*: the backend has no
 * endpoint exposing node coordinates for the road graph in general (only
 * for nodes actually visited by a computed route), so a graph-wide risk
 * overlay is not possible without fabricating coordinates — see
 * `docs/architecture/frontend.md`, "Road-risk visualization", for the
 * full explanation. `route_geometry` has one point per visited node, so
 * consecutive pairs correspond 1:1 with `edge_sequence` entries in order;
 * any length mismatch is treated as unusable data and yields no segments,
 * rather than silently pairing the wrong points.
 */
export function routeToRiskSegments(
  route: RouteResult,
): GeoJsonFeature<GeoJsonLineString, RouteRiskSegmentProperties>[] {
  if (!route.found) return [];
  if (route.route_geometry.length !== route.edge_sequence.length + 1) return [];

  const segments: GeoJsonFeature<GeoJsonLineString, RouteRiskSegmentProperties>[] = [];
  for (let i = 0; i < route.edge_sequence.length; i += 1) {
    const start = route.route_geometry[i];
    const end = route.route_geometry[i + 1];
    const edge = route.edge_sequence[i];
    if (!start || !end || !edge) continue;
    segments.push({
      type: "Feature",
      geometry: { type: "LineString", coordinates: [start, end] },
      properties: { riskLevel: edge.risk_level ?? "unknown", edgeIndex: i },
    });
  }
  return segments;
}

export function routeCollection<TProps>(
  features: GeoJsonFeature<GeoJsonLineString, TProps>[],
): GeoJsonFeatureCollection<GeoJsonLineString, TProps> {
  return { type: "FeatureCollection", features };
}

/** All coordinates a route touches, for fitting the map viewport. */
export function routeBounds(route: RouteResult): GeoJsonPosition[] {
  return route.found ? route.route_geometry : [];
}

/**
 * Computes the same comparison fields the backend's `RouteComparison`
 * exposes (`app/routing/schemas.py`), from two real, independently-fetched
 * `RouteResult`s — the backend has no single endpoint returning a
 * comparison directly (`compare_routes()` is a service-level capability,
 * not an HTTP endpoint — see `apps/api/README.md`, "Route comparison
 * methodology"), so the frontend performs the same, already-documented
 * arithmetic itself. Every input number still comes from the API; nothing
 * here is invented.
 */
export function computeRouteComparison(
  distanceOnly: RouteResult,
  riskAware: RouteResult,
): RouteComparison {
  const bothFound = distanceOnly.found && riskAware.found;

  const distanceDifference =
    bothFound && riskAware.total_distance !== null && distanceOnly.total_distance !== null
      ? riskAware.total_distance - distanceOnly.total_distance
      : null;

  const riskDifference =
    bothFound && riskAware.accumulated_risk !== null && distanceOnly.accumulated_risk !== null
      ? riskAware.accumulated_risk - distanceOnly.accumulated_risk
      : null;

  const detourRatio =
    bothFound &&
    riskAware.total_distance !== null &&
    distanceOnly.total_distance !== null &&
    distanceOnly.total_distance > 0
      ? riskAware.total_distance / distanceOnly.total_distance
      : null;

  const riskReduction =
    bothFound &&
    riskAware.accumulated_risk !== null &&
    distanceOnly.accumulated_risk !== null &&
    distanceOnly.accumulated_risk > 0
      ? 1 - riskAware.accumulated_risk / distanceOnly.accumulated_risk
      : null;

  return {
    distanceOnly,
    riskAware,
    distanceDifference,
    riskDifference,
    routesDiffer: distanceOnly.node_sequence.join(",") !== riskAware.node_sequence.join(","),
    detourRatio,
    riskReduction,
  };
}

export interface BoundingBox {
  west: number;
  south: number;
  east: number;
  north: number;
}

/**
 * The bounding box of every coordinate in a damage feature collection
 * (`Point` and `Polygon` ring vertices alike), or `null` for an empty
 * collection — never a fabricated default location. Trusts the feature
 * collection's coordinates exactly as given, the same convention
 * `components/map/command-map.tsx` uses when auto-fitting the viewport to
 * real data (see `docs/architecture/frontend.md`, "Damage visualization").
 */
export function computeFeatureBounds(collection: DamageFeatureCollection): BoundingBox | null {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  let found = false;

  for (const feature of collection.features) {
    const positions: GeoJsonPosition[] =
      feature.geometry.type === "Point"
        ? [feature.geometry.coordinates]
        : feature.geometry.coordinates.flat();
    for (const [lon, lat] of positions) {
      found = true;
      if (lon < west) west = lon;
      if (lon > east) east = lon;
      if (lat < south) south = lat;
      if (lat > north) north = lat;
    }
  }

  return found ? { west, south, east, north } : null;
}

const EARTH_RADIUS_KM = 6371;

/**
 * Approximate ground area of a bounding box in km², using an
 * equirectangular approximation — accurate enough at the neighborhood/city
 * scale this project operates at (the same order of magnitude
 * `formatDistanceMeters` targets). Deterministic arithmetic over real
 * coordinates: "calculated," not a guess (see `lib/data-provenance.ts`).
 */
export function boundingBoxAreaKm2(box: BoundingBox): number {
  const midLatRad = ((box.north + box.south) / 2) * (Math.PI / 180);
  const widthKm = (box.east - box.west) * (Math.PI / 180) * EARTH_RADIUS_KM * Math.cos(midLatRad);
  const heightKm = (box.north - box.south) * (Math.PI / 180) * EARTH_RADIUS_KM;
  return Math.abs(widthKm * heightKm);
}

export function formatDistanceMeters(meters: number | null): string {
  if (meters === null) return "—";
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`;
  return `${Math.round(meters)} m`;
}

export function formatRiskScore(risk: number | null): string {
  return risk === null ? "—" : risk.toFixed(2);
}

export function formatPercent(fraction: number | null, digits = 1): string {
  return fraction === null ? "—" : `${(fraction * 100).toFixed(digits)}%`;
}

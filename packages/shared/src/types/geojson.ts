/**
 * Minimal RFC 7946 GeoJSON types matching the shapes the backend emits
 * (see `apps/api/app/ml/geospatial/geojson.py`). Deliberately not the full
 * GeoJSON spec (no MultiPoint/LineString/MultiPolygon/GeometryCollection) —
 * only the geometry types the backend's damage-map endpoint can actually
 * produce (`Point`, `Polygon`) plus a generic `LineString` for client-built
 * route geometry (see `lib/geo.ts`).
 */

export type GeoJsonPosition = [longitude: number, latitude: number];

export interface GeoJsonPoint {
  type: "Point";
  coordinates: GeoJsonPosition;
}

export interface GeoJsonPolygon {
  type: "Polygon";
  coordinates: GeoJsonPosition[][];
}

export interface GeoJsonLineString {
  type: "LineString";
  coordinates: GeoJsonPosition[];
}

export type GeoJsonGeometry = GeoJsonPoint | GeoJsonPolygon | GeoJsonLineString;

export interface GeoJsonFeature<
  TGeometry extends GeoJsonGeometry = GeoJsonGeometry,
  TProperties = Record<string, unknown>,
> {
  type: "Feature";
  geometry: TGeometry;
  properties: TProperties;
}

export interface GeoJsonFeatureCollection<
  TGeometry extends GeoJsonGeometry = GeoJsonGeometry,
  TProperties = Record<string, unknown>,
> {
  type: "FeatureCollection";
  features: GeoJsonFeature<TGeometry, TProperties>[];
}

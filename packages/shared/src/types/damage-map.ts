/**
 * Mirrors `apps/api/app/schemas/damage_map.py` and
 * `apps/api/app/ml/geospatial/geojson.py` — the spatial (GeoJSON) damage
 * result served by `GET /api/v1/analysis/{analysis_id}/damage-map`.
 */

import type { AnalysisStatus, DamageClass, DamagePriority } from "./analysis";
import type { GeoJsonFeatureCollection, GeoJsonPoint, GeoJsonPolygon } from "./geojson";

/** The exact five properties the backend puts on every damage feature. */
export interface DamageFeatureProperties {
  building_id: string;
  damage_class: DamageClass;
  confidence: number;
  priority: DamagePriority;
  georeferenced: boolean;
}

export type DamageFeatureCollection = GeoJsonFeatureCollection<
  GeoJsonPoint | GeoJsonPolygon,
  DamageFeatureProperties
> & {
  /** `IMAGE` is source-image pixels; only `EPSG:4326` is map-safe WGS84. */
  coordinate_reference_system: "IMAGE" | "EPSG:4326";
};

export interface DamageMapResponse {
  analysis_id: string;
  status: AnalysisStatus;
  available: boolean;
  reason: string | null;
  feature_collection: DamageFeatureCollection;
}

/**
 * Types mirroring `apps/api/app/schemas/analysis.py` and
 * `apps/api/app/ml/schemas.py` — the analysis upload/lifecycle contract.
 */

export type AnalysisStatus = "uploaded" | "queued" | "processing" | "completed" | "failed";

export type AnalysisErrorCode = "MODEL_UNAVAILABLE" | "INFERENCE_FAILURE";

export interface AnalysisFailure {
  code: AnalysisErrorCode;
  message: string;
}

export interface AnalysisCreateResponse {
  analysis_id: string;
  status: AnalysisStatus;
  filename: string;
}

export type DamageClass = "no_damage" | "minor" | "major" | "destroyed";

/** Damage-based priority only — see `app/ml/geospatial/priority.py`. */
export type DamagePriority = "low" | "medium" | "high" | "critical";

export type CoordinateReferenceSystemName = "image" | "wgs84";

/** A generic bounding box in either pixel or geographic space. */
export interface BoundingBox {
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
}

export interface BuildingDamage {
  building_id: string;
  damage_class: DamageClass;
  confidence: number;
  bounding_box: BoundingBox | null;
  coordinate_reference_system: CoordinateReferenceSystemName;
  georeferenced: boolean;
}

export interface DamageSummary {
  total_buildings: number;
  damaged_buildings: number;
  severely_damaged: number;
  destroyed: number;
}

export interface ModelStatus {
  model_loaded: boolean;
  model_name: string;
  model_version: string;
  device: string;
}

export interface DamageAnalysis {
  analysis_id: string;
  status: AnalysisStatus;
  summary: DamageSummary | null;
  buildings: BuildingDamage[];
  model_metadata: ModelStatus | null;
  failure: AnalysisFailure | null;
  created_at: string | null;
  updated_at: string | null;
}

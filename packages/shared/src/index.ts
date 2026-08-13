export type { ApiResult, HealthStatus, ServiceInfo } from "./types/api";

export type {
  AnalysisStatus,
  AnalysisErrorCode,
  AnalysisFailure,
  AnalysisCreateResponse,
  DamageClass,
  DamagePriority,
  CoordinateReferenceSystemName,
  BoundingBox,
  BuildingDamage,
  DamageSummary,
  ModelStatus,
  DamageAnalysis,
} from "./types/analysis";

export type {
  GeoJsonPosition,
  GeoJsonPoint,
  GeoJsonPolygon,
  GeoJsonLineString,
  GeoJsonGeometry,
  GeoJsonFeature,
  GeoJsonFeatureCollection,
} from "./types/geojson";

export type { DamageFeatureProperties, DamageFeatureCollection, DamageMapResponse } from "./types/damage-map";

export type {
  AccessibilityStatus,
  RiskLevel,
  GeographicCoordinate,
  RiskSource,
  RoadEdge,
  BoundingBoxGeometry,
  RoadNetworkStatusResponse,
} from "./types/roads";

export type { RoadRiskResponse } from "./types/road-risk";

export type {
  RoutingMode,
  AccessibilitySummary,
  RouteResult,
  RoutingRequest,
  RouteComparison,
} from "./types/routing";

export type {
  IncidentSeverity,
  ConfidenceLevel,
  AffectedStructuresSummary,
  IncidentBriefing,
  RouteQuery,
  IncidentSummaryRequest,
} from "./types/incident";

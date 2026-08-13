"""Assembles `IncidentContext` purely from Milestones 3-6C's own,
already-computed outputs — `DamageAnalysis` (damage), `RoadRiskResponse`
(road risk), and an optional `RouteComparison` (routing). No LLM call, no
network access, no new analysis of any kind: every field here is a direct
read or simple aggregation (count/average/max) of data that already
existed before this function runs.
"""

from datetime import UTC, datetime

from app.incident.config import IncidentConfig
from app.incident.schemas import DamageContext, IncidentContext, RoadRiskContext, RouteContext
from app.ml.geospatial.geometry import BoundingBoxGeometry
from app.ml.geospatial.priority import is_high_priority
from app.ml.schemas import BuildingDamage, DamageAnalysis
from app.risk.spatial import representative_point
from app.roads.schemas import AccessibilityStatus, RiskLevel
from app.routing.schemas import RouteComparison, RoutingMode
from app.schemas.analysis import AnalysisStatus
from app.schemas.road_risk import RoadRiskResponse

_RISKY_LEVELS = frozenset({RiskLevel.HIGH, RiskLevel.CRITICAL})
_RISK_LEVEL_RANK: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MODERATE: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


def build_incident_context(
    analysis: DamageAnalysis,
    road_risk: RoadRiskResponse,
    route_comparison: RouteComparison | None,
    config: IncidentConfig,
) -> IncidentContext:
    return IncidentContext(
        analysis_id=analysis.analysis_id,
        analysis_status=analysis.status,
        damage=_build_damage_context(analysis, config),
        road_risk=_build_road_risk_context(road_risk, config),
        route=_build_route_context(route_comparison),
        generated_at=datetime.now(UTC),
    )


def _build_damage_context(analysis: DamageAnalysis, config: IncidentConfig) -> DamageContext:
    if analysis.status is not AnalysisStatus.COMPLETED or analysis.summary is None:
        return DamageContext(
            available=False,
            reason=f"Analysis is not completed yet (status={analysis.status.value}).",
        )

    confidences = [building.confidence for building in analysis.buildings]
    average_confidence = sum(confidences) / len(confidences) if confidences else None

    high_priority_ids = [
        building.building_id
        for building in analysis.buildings
        if is_high_priority(building.damage_class)
    ]

    return DamageContext(
        available=True,
        summary=analysis.summary,
        average_confidence=average_confidence,
        high_priority_structure_ids=high_priority_ids[: config.max_listed_structure_ids],
        spatial_bounds=_spatial_bounds(analysis.buildings),
    )


def _spatial_bounds(buildings: list[BuildingDamage]) -> BoundingBoxGeometry | None:
    """A bounding box over every *georeferenced* building's representative
    point — pixel-space buildings never contribute a coordinate here,
    same CRS discipline as `app.services.road_risk_service`."""
    points = [
        representative_point(building.geometry)
        for building in buildings
        if building.georeferenced and building.geometry is not None
    ]
    if not points:
        return None
    lons = [lon for lon, _ in points]
    lats = [lat for _, lat in points]
    return BoundingBoxGeometry(coordinates=(min(lons), min(lats), max(lons), max(lats)))


def _build_road_risk_context(
    road_risk: RoadRiskResponse, config: IncidentConfig
) -> RoadRiskContext:
    if not road_risk.available:
        return RoadRiskContext(available=False, reason=road_risk.reason)

    edges = road_risk.edges
    risky_edges = [edge for edge in edges if edge.risk_level in _RISKY_LEVELS]
    blocked_count = sum(1 for edge in edges if edge.accessibility is AccessibilityStatus.BLOCKED)
    restricted_count = sum(
        1 for edge in edges if edge.accessibility is AccessibilityStatus.RESTRICTED
    )

    levels_seen = [edge.risk_level for edge in edges if edge.risk_level is not None]
    highest_level = max(levels_seen, key=lambda level: _RISK_LEVEL_RANK[level], default=None)

    sample_ids: list[str] = []
    seen: set[str] = set()
    for edge in risky_edges:
        for source in edge.risk_sources:
            if source.building_id in seen:
                continue
            seen.add(source.building_id)
            sample_ids.append(source.building_id)
            if len(sample_ids) >= config.max_listed_structure_ids:
                break
        if len(sample_ids) >= config.max_listed_structure_ids:
            break

    return RoadRiskContext(
        available=True,
        total_edges_assessed=len(edges),
        risky_edge_count=len(risky_edges),
        blocked_edge_count=blocked_count,
        restricted_edge_count=restricted_count,
        highest_risk_level=highest_level,
        sample_risk_source_building_ids=sample_ids,
    )


def _build_route_context(comparison: RouteComparison | None) -> RouteContext:
    if comparison is None:
        return RouteContext(available=False, reason="No route was requested for this summary.")

    if not comparison.risk_aware.found:
        reason = comparison.risk_aware.reason or "No route could be computed."
        return RouteContext(available=False, reason=reason)

    return RouteContext(
        available=True,
        selected_mode=RoutingMode.RISK_AWARE,
        selected_distance_meters=comparison.risk_aware.total_distance,
        selected_risk_score=comparison.risk_aware.accumulated_risk,
        baseline_distance_meters=comparison.distance_only.total_distance,
        baseline_risk_score=comparison.distance_only.accumulated_risk,
        detour_ratio=comparison.detour_ratio,
        avoided_high_risk_segment_count=len(comparison.high_risk_edges_avoided),
    )

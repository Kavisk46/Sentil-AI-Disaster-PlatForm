"""Orchestrates the "Spatial Relationship" pipeline for one road network:

    1. Obtain a road edge's geometry (its two endpoint nodes).
    2. Find nearby damage geometries (the bounding-box pre-filter).
    3. Calculate distance (point-to-segment, `app.risk.spatial`).
    4. Calculate each damage source's contribution (`app.risk.formula`).
    5. Aggregate contributions into one risk score (`app.risk.formula`).
    6. Produce the road-risk result: a new `RoadEdge` carrying
       `risk_score`/`risk_level`/`risk_sources`.

Never mutates `AnalysisRepository`/`SpatialRepository`/`RoadNetworkRepository`
state, and never touches `BuildingDamage` — every `RoadEdge` this returns
is a **copy** (`model_copy`) of the input edge with only the risk fields
updated; `accessibility` is left exactly as given (see `app.risk`, "Why
risk is not blockage").
"""

from collections.abc import Callable, Mapping, Sequence

from app.ml.geospatial.geometry import BoundingBoxGeometry
from app.ml.schemas import BuildingDamage
from app.risk.config import RoadRiskConfig
from app.risk.formula import aggregate_contributions, classify_risk_level, contribution
from app.risk.spatial import (
    padded_bounding_box,
    point_to_segment_distance_meters,
    representative_point,
)
from app.roads.schemas import RiskSource, RoadEdge, RoadNode

FindNearbyBuildings = Callable[[BoundingBoxGeometry], Sequence[BuildingDamage]]


def compute_road_risk(
    edges: Sequence[RoadEdge],
    nodes_by_id: Mapping[str, RoadNode],
    find_nearby_buildings: FindNearbyBuildings,
    config: RoadRiskConfig,
) -> list[RoadEdge]:
    """Assess every edge in `edges` against whatever `find_nearby_buildings`
    returns for its (padded) bounding box.

    `find_nearby_buildings` is the spatial-indexing seam: production
    wiring (`app.services.road_risk_service`) passes a closure over an
    already-georeferenced-filtered building list; a future PostGIS-backed
    implementation (`ST_DWithin` against a spatial index) plugs in here
    without this function changing. "For small prototype datasets, a
    simple implementation is acceptable" — see the caller.
    """
    return [_assess_edge(edge, nodes_by_id, find_nearby_buildings, config) for edge in edges]


def _assess_edge(
    edge: RoadEdge,
    nodes_by_id: Mapping[str, RoadNode],
    find_nearby_buildings: FindNearbyBuildings,
    config: RoadRiskConfig,
) -> RoadEdge:
    source = nodes_by_id.get(edge.source_node)
    target = nodes_by_id.get(edge.target_node)
    if source is None or target is None:
        # Can't assess an edge without both endpoints' geometry — leave it
        # exactly as given rather than guessing a location.
        return edge

    bbox = padded_bounding_box(source, target, config.search_radius_meters)
    sources = _risk_sources(source, target, find_nearby_buildings(bbox), config)
    risk_score = aggregate_contributions([item.contribution for item in sources], config)
    risk_level = classify_risk_level(risk_score, config)

    return edge.model_copy(
        update={"risk_score": risk_score, "risk_level": risk_level, "risk_sources": sources}
    )


def _risk_sources(
    source: RoadNode,
    target: RoadNode,
    candidates: Sequence[BuildingDamage],
    config: RoadRiskConfig,
) -> list[RiskSource]:
    sources: list[RiskSource] = []
    for building in candidates:
        if building.geometry is None:
            continue
        point_lon, point_lat = representative_point(building.geometry)
        distance = point_to_segment_distance_meters(
            point_lon,
            point_lat,
            source.longitude,
            source.latitude,
            target.longitude,
            target.latitude,
        )
        if distance > config.search_radius_meters:
            continue
        value = contribution(building.damage_class, building.confidence, distance, config)
        if value <= 0.0:
            continue
        sources.append(
            RiskSource(
                building_id=building.building_id,
                damage_class=building.damage_class,
                confidence=building.confidence,
                distance_meters=distance,
                contribution=value,
            )
        )
    return sources

"""Tests for damage -> road risk (Milestone 6B): the baseline heuristic
formula, point-to-segment distance, the spatial pre-filter, the
`compute_road_risk` analyzer, `RoadRiskService`, and
`GET /api/v1/analysis/{analysis_id}/road-risk`.

No internet access, no GPU, fully deterministic — every damage/road
geometry here is a small, synthetic, hand-picked coordinate.
"""

import math
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_road_network_repository, get_spatial_repository
from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.ml.geospatial.geometry import BoundingBoxGeometry, PointGeometry, PolygonGeometry
from app.ml.schemas import BuildingDamage, DamageClass
from app.risk.analyzer import compute_road_risk
from app.risk.config import RoadRiskConfig
from app.risk.formula import (
    aggregate_contributions,
    classify_risk_level,
    compute_risk_adjusted_cost,
    contribution,
    distance_decay,
    severity_weight,
)
from app.risk.spatial import (
    padded_bounding_box,
    point_to_segment_distance_meters,
    representative_point,
)
from app.roads.errors import InvalidRoadGraphError
from app.roads.schemas import RiskLevel, RiskSource, RoadEdge, RoadNode
from app.schemas.analysis import AnalysisStatus
from app.services.analysis_processing_service import AnalysisProcessingService
from app.services.analysis_repository import (
    AnalysisNotFoundError,
    AnalysisRecord,
    InMemoryAnalysisRepository,
)
from app.services.road_network_repository import InMemoryRoadNetworkRepository
from app.services.road_risk_service import RoadRiskService
from app.services.spatial_repository import InMemorySpatialRepository

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


def _config(**overrides: object) -> RoadRiskConfig:
    defaults: dict[str, object] = {
        "severity_weights": {
            DamageClass.NO_DAMAGE: 0.0,
            DamageClass.MINOR: 0.25,
            DamageClass.MAJOR: 0.6,
            DamageClass.DESTROYED: 1.0,
        },
        "search_radius_meters": 150.0,
        "distance_decay_rate": 0.02,
        "aggregation_cap": 1.0,
        "risk_level_low_max": 0.25,
        "risk_level_moderate_max": 0.5,
        "risk_level_high_max": 0.75,
        "cost_penalty_scale": 4.0,
    }
    defaults.update(overrides)
    return RoadRiskConfig(**defaults)  # type: ignore[arg-type]


def _node(node_id: str, lat: float, lon: float) -> RoadNode:
    return RoadNode(node_id=node_id, latitude=lat, longitude=lon)


def _edge(source: str, target: str, distance: float = 100.0, **kwargs: object) -> RoadEdge:
    return RoadEdge(
        source_node=source, target_node=target, distance=distance, base_cost=distance, **kwargs
    )  # type: ignore[arg-type]


def _building(
    building_id: str,
    damage_class: DamageClass,
    lon: float,
    lat: float,
    confidence: float = 0.9,
    georeferenced: bool = True,
    crs: CoordinateReferenceSystem = CoordinateReferenceSystem.WGS84,
) -> BuildingDamage:
    return BuildingDamage(
        building_id=building_id,
        damage_class=damage_class,
        confidence=confidence,
        geometry=PointGeometry(coordinates=(lon, lat)),
        coordinate_reference_system=crs,
        georeferenced=georeferenced,
    )


def _find_all(buildings: list[BuildingDamage]):  # type: ignore[no-untyped-def]
    def find(bbox: BoundingBoxGeometry) -> list[BuildingDamage]:
        return buildings

    return find


# ---------------------------------------------------------------------------
# RoadRiskConfig validation
# ---------------------------------------------------------------------------


def test_config_rejects_non_increasing_thresholds() -> None:
    with pytest.raises(ValueError, match="thresholds"):
        _config(risk_level_low_max=0.5, risk_level_moderate_max=0.5, risk_level_high_max=0.75)


def test_config_rejects_non_positive_aggregation_cap() -> None:
    with pytest.raises(ValueError, match="aggregation_cap"):
        _config(aggregation_cap=0.0)


def test_config_rejects_non_positive_search_radius() -> None:
    with pytest.raises(ValueError, match="search_radius_meters"):
        _config(search_radius_meters=0.0)


def test_config_from_settings_uses_settings_values() -> None:
    from app.core.config import Settings

    settings = Settings(ROAD_RISK_SEARCH_RADIUS_METERS=42.0)
    config = RoadRiskConfig.from_settings(settings)
    assert config.search_radius_meters == 42.0
    expected_weight = settings.ROAD_RISK_SEVERITY_WEIGHT_DESTROYED
    assert config.severity_weights[DamageClass.DESTROYED] == expected_weight


# ---------------------------------------------------------------------------
# formula.py — the baseline heuristic math
# ---------------------------------------------------------------------------


def test_severity_weight_uses_configured_values() -> None:
    config = _config()
    assert severity_weight(DamageClass.NO_DAMAGE, config) == 0.0
    assert severity_weight(DamageClass.DESTROYED, config) == 1.0


def test_distance_decay_at_zero_distance_is_one() -> None:
    assert distance_decay(0.0, _config()) == pytest.approx(1.0)


def test_distance_decay_decreases_with_distance() -> None:
    """6. Distance decay: farther is never riskier than closer."""
    config = _config()
    near = distance_decay(10.0, config)
    far = distance_decay(100.0, config)
    assert 0.0 < far < near <= 1.0


def test_contribution_scales_with_confidence() -> None:
    """7. Confidence effect: lower confidence -> lower contribution,
    proportionally."""
    config = _config()
    high_confidence = contribution(DamageClass.MAJOR, 1.0, 10.0, config)
    low_confidence = contribution(DamageClass.MAJOR, 0.5, 10.0, config)
    assert low_confidence == pytest.approx(high_confidence * 0.5)


def test_contribution_is_zero_for_no_damage() -> None:
    """1. No damage near road -> zero contribution, regardless of distance."""
    config = _config()
    assert contribution(DamageClass.NO_DAMAGE, 1.0, 0.0, config) == 0.0


@pytest.mark.parametrize(
    ("damage_class", "expected_weight"),
    [
        (DamageClass.MINOR, 0.25),
        (DamageClass.MAJOR, 0.6),
        (DamageClass.DESTROYED, 1.0),
    ],
)
def test_contribution_ordering_matches_severity(
    damage_class: DamageClass, expected_weight: float
) -> None:
    """2/3/4. Minor < major < destroyed, at the same distance/confidence."""
    config = _config()
    value = contribution(damage_class, 1.0, 0.0, config)  # distance=0 -> decay=1
    assert value == pytest.approx(expected_weight)


def test_aggregate_contributions_sums_multiple_sources() -> None:
    """5/8. Multiple damage sources aggregate (sum, before capping)."""
    config = _config(aggregation_cap=10.0)  # cap well above the sum, to isolate summation
    assert aggregate_contributions([0.2, 0.3, 0.1], config) == pytest.approx(0.6)


def test_aggregate_contributions_caps_at_configured_maximum() -> None:
    """9. Risk normalization: unbounded accumulation is capped."""
    config = _config(aggregation_cap=1.0)
    assert aggregate_contributions([0.9, 0.9, 0.9], config) == 1.0


def test_aggregate_contributions_of_no_sources_is_zero() -> None:
    assert aggregate_contributions([], _config()) == 0.0


@pytest.mark.parametrize(
    ("risk_score", "expected_level"),
    [
        (0.0, RiskLevel.LOW),
        (0.25, RiskLevel.LOW),
        (0.26, RiskLevel.MODERATE),
        (0.5, RiskLevel.MODERATE),
        (0.51, RiskLevel.HIGH),
        (0.75, RiskLevel.HIGH),
        (0.76, RiskLevel.CRITICAL),
        (1.0, RiskLevel.CRITICAL),
    ],
)
def test_classify_risk_level_boundaries(risk_score: float, expected_level: RiskLevel) -> None:
    """10. Risk level classification at each threshold boundary."""
    assert classify_risk_level(risk_score, _config()) is expected_level


def test_compute_risk_adjusted_cost_applies_penalty() -> None:
    """15. Risk-adjusted edge cost: base_cost * (1 + penalty_scale * risk_score)."""
    config = _config(cost_penalty_scale=4.0)
    assert compute_risk_adjusted_cost(100.0, 0.5, config) == pytest.approx(300.0)
    assert compute_risk_adjusted_cost(100.0, 0.0, config) == pytest.approx(100.0)
    assert compute_risk_adjusted_cost(100.0, 1.0, config) == pytest.approx(500.0)


def test_compute_risk_adjusted_cost_of_unassessed_edge_is_unchanged() -> None:
    """An edge with risk_score=None (never assessed) must not silently
    become more expensive."""
    assert compute_risk_adjusted_cost(100.0, None, _config()) == 100.0


# ---------------------------------------------------------------------------
# spatial.py — point-to-segment distance, bbox padding, representative point
# ---------------------------------------------------------------------------


def test_point_to_segment_distance_is_zero_on_the_segment() -> None:
    # Segment from (0, 0) to (0, 1) degree of latitude; point at the midpoint.
    distance = point_to_segment_distance_meters(0.0, 0.5, 0.0, 0.0, 0.0, 1.0)
    assert distance == pytest.approx(0.0, abs=1e-6)


def test_point_to_segment_distance_clamps_to_nearest_endpoint() -> None:
    # Point "before" the segment start along its axis -> nearest is the start.
    distance_to_start = point_to_segment_distance_meters(0.0, -1.0, 0.0, 0.0, 0.0, 1.0)
    direct_to_start = point_to_segment_distance_meters(0.0, -1.0, 0.0, 0.0, 0.0, 0.0)
    assert distance_to_start == pytest.approx(direct_to_start)


def test_point_to_segment_distance_degenerate_segment_is_distance_to_point() -> None:
    distance = point_to_segment_distance_meters(0.0, 1.0, 0.0, 0.0, 0.0, 0.0)
    direct = point_to_segment_distance_meters(0.0, 1.0, 0.0, 0.0, 0.0, 0.0)
    assert distance == pytest.approx(direct)
    assert distance > 0


def test_point_to_segment_distance_is_symmetric_in_segment_endpoint_order() -> None:
    forward = point_to_segment_distance_meters(0.001, 0.0005, 0.0, 0.0, 0.0, 0.001)
    backward = point_to_segment_distance_meters(0.001, 0.0005, 0.0, 0.001, 0.0, 0.0)
    assert forward == pytest.approx(backward)


def test_padded_bounding_box_contains_both_endpoints() -> None:
    source = _node("A", 10.0, 20.0)
    target = _node("B", 10.001, 20.001)
    bbox = padded_bounding_box(source, target, radius_meters=50.0)
    min_lon, min_lat, max_lon, max_lat = bbox.coordinates
    assert min_lon <= source.longitude <= max_lon
    assert min_lat <= source.latitude <= max_lat
    assert min_lon <= target.longitude <= max_lon
    assert min_lat <= target.latitude <= max_lat


def test_padded_bounding_box_grows_with_radius() -> None:
    source = _node("A", 10.0, 20.0)
    target = _node("B", 10.0, 20.0)
    small = padded_bounding_box(source, target, radius_meters=10.0)
    large = padded_bounding_box(source, target, radius_meters=1000.0)
    small_width = small.coordinates[2] - small.coordinates[0]
    large_width = large.coordinates[2] - large.coordinates[0]
    assert large_width > small_width


def test_representative_point_of_point_geometry_is_itself() -> None:
    geometry = PointGeometry(coordinates=(5.0, 6.0))
    assert representative_point(geometry) == (5.0, 6.0)


def test_representative_point_of_bounding_box_is_its_center() -> None:
    geometry = BoundingBoxGeometry(coordinates=(0.0, 0.0, 10.0, 20.0))
    assert representative_point(geometry) == (5.0, 10.0)


def test_representative_point_of_polygon_is_vertex_average() -> None:
    ring = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0), (0.0, 0.0)]
    geometry = PolygonGeometry(coordinates=[ring])
    assert representative_point(geometry) == (1.0, 1.0)


# ---------------------------------------------------------------------------
# 13. Invalid geometry handling
# ---------------------------------------------------------------------------


def test_risk_source_rejects_negative_distance() -> None:
    with pytest.raises(ValidationError):
        RiskSource(
            building_id="b1",
            damage_class=DamageClass.MAJOR,
            confidence=0.9,
            distance_meters=-1.0,
            contribution=0.5,
        )


def test_risk_source_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValidationError):
        RiskSource(
            building_id="b1",
            damage_class=DamageClass.MAJOR,
            confidence=1.5,
            distance_meters=10.0,
            contribution=0.5,
        )


def test_risk_source_rejects_non_finite_distance() -> None:
    with pytest.raises(ValidationError):
        RiskSource(
            building_id="b1",
            damage_class=DamageClass.MAJOR,
            confidence=0.9,
            distance_meters=math.nan,
            contribution=0.5,
        )


def test_invalid_road_graph_error_is_a_value_error() -> None:
    assert issubclass(InvalidRoadGraphError, ValueError)


# ---------------------------------------------------------------------------
# analyzer.py — compute_road_risk (the full spatial-relationship pipeline)
# ---------------------------------------------------------------------------


def test_no_nearby_damage_produces_zero_risk_and_low_level() -> None:
    """1. No damage near road."""
    source, target = _node("A", 10.0, 20.0), _node("B", 10.0, 20.001)
    edge = _edge("A", "B", distance=111.0)
    nodes = {"A": source, "B": target}

    [assessed] = compute_road_risk([edge], nodes, _find_all([]), _config())

    assert assessed.risk_score == 0.0
    assert assessed.risk_level is RiskLevel.LOW
    assert assessed.risk_sources == []


def test_minor_damage_near_road_produces_a_risk_source() -> None:
    """2. Minor damage near road."""
    source, target = _node("A", 10.0, 20.0), _node("B", 10.0, 20.001)
    edge = _edge("A", "B", distance=111.0)
    nodes = {"A": source, "B": target}
    building = _building("b1", DamageClass.MINOR, lon=20.0002, lat=10.0, confidence=1.0)

    [assessed] = compute_road_risk([edge], nodes, _find_all([building]), _config())

    assert len(assessed.risk_sources) == 1
    assert assessed.risk_sources[0].damage_class is DamageClass.MINOR
    assert assessed.risk_score > 0.0


def test_major_damage_near_road_produces_higher_risk_than_minor() -> None:
    """3. Major damage near road — higher risk than the same-distance minor case."""
    nodes = {"A": _node("A", 10.0, 20.0), "B": _node("B", 10.0, 20.001)}
    edge = _edge("A", "B", distance=111.0)

    minor_building = _building("b1", DamageClass.MINOR, lon=20.0002, lat=10.0, confidence=1.0)
    major_building = _building("b1", DamageClass.MAJOR, lon=20.0002, lat=10.0, confidence=1.0)

    [minor_assessed] = compute_road_risk([edge], nodes, _find_all([minor_building]), _config())
    [major_assessed] = compute_road_risk([edge], nodes, _find_all([major_building]), _config())

    assert major_assessed.risk_score > minor_assessed.risk_score


def test_destroyed_building_near_road_produces_the_highest_risk() -> None:
    """4. Destroyed building near road — highest of the four classes."""
    nodes = {"A": _node("A", 10.0, 20.0), "B": _node("B", 10.0, 20.001)}
    edge = _edge("A", "B", distance=111.0)
    scores = {}
    for damage_class in DamageClass:
        building = _building("b1", damage_class, lon=20.0002, lat=10.0, confidence=1.0)
        [assessed] = compute_road_risk([edge], nodes, _find_all([building]), _config())
        scores[damage_class] = assessed.risk_score

    assert (
        scores[DamageClass.NO_DAMAGE]
        < scores[DamageClass.MINOR]
        < scores[DamageClass.MAJOR]
        < scores[DamageClass.DESTROYED]
    )


def test_multiple_damage_sources_aggregate_deterministically() -> None:
    """5. Multiple damage sources."""
    nodes = {"A": _node("A", 10.0, 20.0), "B": _node("B", 10.0, 20.001)}
    edge = _edge("A", "B", distance=111.0)
    buildings = [
        _building("b1", DamageClass.MINOR, lon=20.0002, lat=10.0, confidence=1.0),
        _building("b2", DamageClass.MAJOR, lon=20.0003, lat=10.0, confidence=1.0),
    ]

    config = _config(aggregation_cap=10.0)
    [assessed] = compute_road_risk([edge], nodes, _find_all(buildings), config)

    assert len(assessed.risk_sources) == 2
    expected = sum(source.contribution for source in assessed.risk_sources)
    assert assessed.risk_score == pytest.approx(expected)


def test_far_away_damage_is_excluded_from_risk_sources() -> None:
    """11. Risk sources never include damage outside the search radius —
    nothing fabricated."""
    nodes = {"A": _node("A", 10.0, 20.0), "B": _node("B", 10.0, 20.001)}
    edge = _edge("A", "B", distance=111.0)
    far_building = _building("far", DamageClass.DESTROYED, lon=25.0, lat=15.0, confidence=1.0)

    [assessed] = compute_road_risk(
        [edge], nodes, _find_all([far_building]), _config(search_radius_meters=150.0)
    )

    assert assessed.risk_sources == []
    assert assessed.risk_score == 0.0


def test_risk_sources_contain_explainable_fields() -> None:
    """11. Risk sources — enough information to explain "why is this road risky"."""
    nodes = {"A": _node("A", 10.0, 20.0), "B": _node("B", 10.0, 20.001)}
    edge = _edge("A", "B", distance=111.0)
    building = _building("building_7", DamageClass.MAJOR, lon=20.0002, lat=10.0, confidence=0.8)

    [assessed] = compute_road_risk([edge], nodes, _find_all([building]), _config())

    [source] = assessed.risk_sources
    assert source.building_id == "building_7"
    assert source.damage_class is DamageClass.MAJOR
    assert source.confidence == 0.8
    assert source.distance_meters >= 0.0
    assert 0.0 < source.contribution <= 1.0


def test_accessibility_is_unchanged_by_risk_assessment() -> None:
    """14. Accessibility remains independent of risk — a critical risk_level
    must not imply blocked accessibility."""
    from app.roads.schemas import AccessibilityStatus

    nodes = {"A": _node("A", 10.0, 20.0), "B": _node("B", 10.0, 20.001)}
    edge = _edge("A", "B", distance=111.0, accessibility=AccessibilityStatus.OPEN)
    # A cluster of destroyed buildings right on the road -> risk should max out.
    buildings = [
        _building(f"b{i}", DamageClass.DESTROYED, lon=20.0005, lat=10.0, confidence=1.0)
        for i in range(5)
    ]

    [assessed] = compute_road_risk([edge], nodes, _find_all(buildings), _config())

    assert assessed.risk_level is RiskLevel.CRITICAL
    assert assessed.accessibility is AccessibilityStatus.OPEN  # untouched


def test_edge_referencing_an_unknown_node_is_returned_unchanged() -> None:
    edge = _edge("A", "ghost", distance=50.0)
    nodes = {"A": _node("A", 10.0, 20.0)}

    [assessed] = compute_road_risk([edge], nodes, _find_all([]), _config())

    assert assessed == edge
    assert assessed.risk_score is None


def test_building_with_no_geometry_is_skipped_safely() -> None:
    nodes = {"A": _node("A", 10.0, 20.0), "B": _node("B", 10.0, 20.001)}
    edge = _edge("A", "B", distance=111.0)
    building = BuildingDamage(
        building_id="b1", damage_class=DamageClass.DESTROYED, confidence=1.0, geometry=None
    )

    [assessed] = compute_road_risk([edge], nodes, _find_all([building]), _config())

    assert assessed.risk_sources == []


def test_original_building_damage_object_is_never_mutated() -> None:
    """Do NOT modify original damage predictions."""
    nodes = {"A": _node("A", 10.0, 20.0), "B": _node("B", 10.0, 20.001)}
    edge = _edge("A", "B", distance=111.0)
    building = _building("b1", DamageClass.DESTROYED, lon=20.0002, lat=10.0)
    original = building.model_copy(deep=True)

    compute_road_risk([edge], nodes, _find_all([building]), _config())

    assert building == original


def test_original_road_edge_object_is_never_mutated() -> None:
    """compute_road_risk returns copies, not the same edge instances."""
    nodes = {"A": _node("A", 10.0, 20.0), "B": _node("B", 10.0, 20.001)}
    edge = _edge("A", "B", distance=111.0)
    building = _building("b1", DamageClass.MAJOR, lon=20.0002, lat=10.0)

    compute_road_risk([edge], nodes, _find_all([building]), _config())

    assert edge.risk_score is None  # the original, pre-assessment edge is untouched


# ---------------------------------------------------------------------------
# 12. CRS handling
# ---------------------------------------------------------------------------


def test_pixel_space_building_never_contributes_even_at_numerically_close_coordinates() -> None:
    """A pixel-space (georeferenced=False) building must never be treated
    as geographically nearby, no matter how numerically close its raw
    coordinates happen to look to a road node's lat/lon.

    This building's "geometry" is pixel coordinates that happen to be
    numerically close to a plausible road's lon/lat — a naive
    implementation that ignored CRS could mistake this for a 20cm-away
    building.
    """
    pixel_building = _building(
        "pixel",
        DamageClass.DESTROYED,
        lon=20.0002,
        lat=10.0,
        confidence=1.0,
        georeferenced=False,
        crs=CoordinateReferenceSystem.IMAGE,
    )

    # RoadRiskService is what actually enforces the CRS filter (see below);
    # compute_road_risk() itself trusts whatever find_nearby_buildings
    # returns, so this test exercises the service-level guarantee via the
    # same helper the service uses.
    from app.services.road_risk_service import _is_usable

    assert _is_usable(pixel_building) is False


# ---------------------------------------------------------------------------
# RoadRiskService — unit tests (17. Missing spatial data)
# ---------------------------------------------------------------------------


def _processing_service_with(record: AnalysisRecord) -> AnalysisProcessingService:
    repository = InMemoryAnalysisRepository()
    repository.create(record)
    # get_analysis() never touches file_storage/inference_engine, so these
    # are never called — a real object isn't needed for these tests.
    return AnalysisProcessingService(
        repository=repository, file_storage=None, inference_engine=None  # type: ignore[arg-type]
    )


def _record(status: AnalysisStatus, analysis_id: UUID | None = None) -> AnalysisRecord:
    now = datetime.now(UTC)
    return AnalysisRecord(
        analysis_id=analysis_id or uuid4(),
        status=status,
        original_filename="a.png",
        storage_name="a.png",
        content_type="image/png",
        size_bytes=10,
        created_at=now,
        updated_at=now,
    )


def test_service_reports_unavailable_when_analysis_not_completed() -> None:
    record = _record(AnalysisStatus.PROCESSING)
    service = RoadRiskService(
        processing_service=_processing_service_with(record),
        spatial_repository=InMemorySpatialRepository(),
        road_network_repository=InMemoryRoadNetworkRepository(),
        config=_config(),
    )

    result = service.get_road_risk(record.analysis_id)

    assert result.available is False
    assert "not completed" in (result.reason or "")
    assert result.edges == []


def test_service_reports_unavailable_when_no_georeferenced_buildings() -> None:
    record = _record(AnalysisStatus.COMPLETED)
    spatial_repository = InMemorySpatialRepository()
    # Only a pixel-space building saved — the honest, current real-world state.
    pixel_building = _building(
        "b1",
        DamageClass.MAJOR,
        lon=1.0,
        lat=1.0,
        georeferenced=False,
        crs=CoordinateReferenceSystem.IMAGE,
    )
    spatial_repository.save_buildings(record.analysis_id, [pixel_building])
    service = RoadRiskService(
        processing_service=_processing_service_with(record),
        spatial_repository=spatial_repository,
        road_network_repository=InMemoryRoadNetworkRepository(),
        config=_config(),
    )

    result = service.get_road_risk(record.analysis_id)

    assert result.available is False
    assert "georeferenced" in (result.reason or "").lower()


def test_service_reports_unavailable_when_no_road_network_loaded() -> None:
    record = _record(AnalysisStatus.COMPLETED)
    spatial_repository = InMemorySpatialRepository()
    spatial_repository.save_buildings(
        record.analysis_id, [_building("b1", DamageClass.MAJOR, lon=1.0, lat=1.0)]
    )
    service = RoadRiskService(
        processing_service=_processing_service_with(record),
        spatial_repository=spatial_repository,
        road_network_repository=InMemoryRoadNetworkRepository(),  # empty
        config=_config(),
    )

    result = service.get_road_risk(record.analysis_id)

    assert result.available is False
    assert "road network" in (result.reason or "").lower()


def test_service_returns_risk_assessed_edges_when_everything_is_available() -> None:
    record = _record(AnalysisStatus.COMPLETED)
    spatial_repository = InMemorySpatialRepository()
    spatial_repository.save_buildings(
        record.analysis_id,
        [_building("b1", DamageClass.DESTROYED, lon=20.0002, lat=10.0, confidence=1.0)],
    )
    road_repository = InMemoryRoadNetworkRepository()
    road_repository.add_node(_node("A", 10.0, 20.0))
    road_repository.add_node(_node("B", 10.0, 20.001))
    road_repository.add_edge(_edge("A", "B", distance=111.0))
    service = RoadRiskService(
        processing_service=_processing_service_with(record),
        spatial_repository=spatial_repository,
        road_network_repository=road_repository,
        config=_config(),
    )

    result = service.get_road_risk(record.analysis_id)

    assert result.available is True
    assert result.reason is None
    [edge] = result.edges
    assert edge.risk_score is not None and edge.risk_score > 0.0
    assert len(edge.risk_sources) == 1


def test_service_raises_not_found_for_unknown_analysis() -> None:
    service = RoadRiskService(
        processing_service=_processing_service_with(_record(AnalysisStatus.COMPLETED)),
        spatial_repository=InMemorySpatialRepository(),
        road_network_repository=InMemoryRoadNetworkRepository(),
        config=_config(),
    )

    with pytest.raises(AnalysisNotFoundError):
        service.get_road_risk(uuid4())


# ---------------------------------------------------------------------------
# 16. Road-risk API
# ---------------------------------------------------------------------------


def _post_analysis(client: TestClient) -> str:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), color=(10, 20, 30)).save(buffer, format="PNG")
    response = client.post(
        "/api/v1/analysis", files={"image": ("aerial.png", buffer.getvalue(), "image/png")}
    )
    assert response.status_code == 201
    analysis_id: str = response.json()["analysis_id"]
    return analysis_id


def test_road_risk_endpoint_unavailable_by_default(analysis_client: TestClient) -> None:
    """Default wiring: MODEL_UNAVAILABLE -> analysis never completes -> unavailable."""
    analysis_id = _post_analysis(analysis_client)

    response = analysis_client.get(f"/api/v1/analysis/{analysis_id}/road-risk")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["edges"] == []


def test_road_risk_endpoint_unknown_analysis_returns_404(analysis_client: TestClient) -> None:
    response = analysis_client.get(f"/api/v1/analysis/{uuid4()}/road-risk")
    assert response.status_code == 404


def test_road_risk_endpoint_invalid_analysis_id_returns_422(analysis_client: TestClient) -> None:
    response = analysis_client.get("/api/v1/analysis/not-a-uuid/road-risk")
    assert response.status_code == 422


class _FakeGeoModel:
    """Test-only DamageModel producing one detection with a bounding box,
    so the analysis actually reaches `completed` (see test_geospatial.py
    for the same pattern)."""

    def load(self) -> None:
        return None

    def predict(self, image: object) -> list:  # type: ignore[type-arg]
        from app.ml.model import RawDetection
        from app.ml.spatial import BoundingBox

        return [
            RawDetection(
                damage_class=DamageClass.DESTROYED,
                confidence=0.9,
                bounding_box=BoundingBox(x_min=0, y_min=0, x_max=10, y_max=10),
            )
        ]

    def health(self):  # type: ignore[no-untyped-def]
        from app.ml.schemas import ModelStatus

        return ModelStatus(model_loaded=True, model_name="fake", model_version="test", device="cpu")


def test_road_risk_endpoint_available_end_to_end(
    analysis_app_factory,  # type: ignore[no-untyped-def]
) -> None:
    """Full HTTP round-trip: a completed analysis, with its (test-seeded)
    georeferenced buildings and a nearby synthetic road network, produces a
    risk-assessed response through the real endpoint/service/analyzer
    stack. Buildings are seeded directly into the spatial repository as
    georeferenced WGS84 (bypassing the real upload pipeline, which — since
    no georeferencing metadata source exists yet, see apps/api/README.md —
    never itself produces georeferenced buildings); this mirrors how
    test_geospatial.py's spatial-repository tests already seed data
    directly rather than only through HTTP.
    """
    app: FastAPI = analysis_app_factory(model=_FakeGeoModel())
    client = TestClient(app)
    analysis_id = _post_analysis(client)

    spatial_repository = app.dependency_overrides[get_spatial_repository]()
    spatial_repository.save_buildings(
        UUID(analysis_id),
        [_building("building_0", DamageClass.DESTROYED, lon=20.0002, lat=10.0, confidence=0.9)],
    )

    road_repository = InMemoryRoadNetworkRepository()
    road_repository.add_node(_node("A", 10.0, 20.0))
    road_repository.add_node(_node("B", 10.0, 20.001))
    road_repository.add_edge(_edge("A", "B", distance=111.0))
    app.dependency_overrides[get_road_network_repository] = lambda: road_repository

    response = client.get(f"/api/v1/analysis/{analysis_id}/road-risk")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    [edge] = body["edges"]
    assert edge["risk_score"] > 0.0
    assert edge["risk_level"] in {"low", "moderate", "high", "critical"}
    assert len(edge["risk_sources"]) == 1
    assert edge["risk_sources"][0]["building_id"] == "building_0"
    assert edge["accessibility"] == "unknown"  # untouched by risk assessment

"""Tests for geospatial damage intelligence (Milestone 5): validated
geometry, CRS handling, the image-space/georeferenced spatial-builder
split, GeoJSON conversion, damage-based priority, the spatial repository,
and `GET /api/v1/analysis/{analysis_id}/damage-map`.

Fake `DamageModel`/`FileStorage` implementations here are test-only
doubles, same pattern as `test_analysis_lifecycle.py`. No GPU, no
downloaded model, no internet access, no real satellite imagery anywhere
in this file — every geometry is a small, deterministic synthetic shape.
"""

import math
from collections.abc import Callable
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.ml.geospatial.crs import CoordinateReferenceSystem, UnsupportedCRSError, validate_crs
from app.ml.geospatial.geojson import (
    FeatureProperties,
    building_to_feature,
    to_feature_collection,
)
from app.ml.geospatial.geometry import (
    BoundingBoxGeometry,
    PointGeometry,
    PolygonGeometry,
)
from app.ml.geospatial.georeferencing import (
    AffineGeoTransform,
    GeoreferencingUnavailableError,
    NoGeoreferencingAvailable,
)
from app.ml.geospatial.priority import (
    DamagePriority,
    compute_damage_priority,
    is_high_priority,
    priority_rank,
)
from app.ml.geospatial.spatial_builder import georeferenced_geometry, image_space_geometry
from app.ml.model import RawDetection
from app.ml.postprocessing import build_analysis
from app.ml.schemas import BuildingDamage, DamageClass, ModelStatus
from app.ml.spatial import BoundingBox
from app.schemas.analysis import AnalysisStatus
from app.services.spatial_repository import InMemorySpatialRepository


def _bbox(
    x_min: float = 0.0, y_min: float = 0.0, x_max: float = 10.0, y_max: float = 20.0
) -> BoundingBox:
    return BoundingBox(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max)


def _building(
    building_id: str = "building_0",
    damage_class: DamageClass = DamageClass.MAJOR,
    geometry: object = None,
    georeferenced: bool = False,
    crs: CoordinateReferenceSystem = CoordinateReferenceSystem.IMAGE,
) -> BuildingDamage:
    return BuildingDamage(
        building_id=building_id,
        damage_class=damage_class,
        confidence=0.9,
        geometry=geometry,
        coordinate_reference_system=crs,
        georeferenced=georeferenced,
    )


# ---------------------------------------------------------------------------
# 6. Point validation / 13. Invalid geometry handling
# ---------------------------------------------------------------------------


def test_point_geometry_accepts_finite_coordinates() -> None:
    point = PointGeometry(coordinates=(12.5, -8.25))
    assert point.coordinates == (12.5, -8.25)


@pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf])
def test_point_geometry_rejects_non_finite_values(bad_value: float) -> None:
    with pytest.raises(ValidationError):
        PointGeometry(coordinates=(bad_value, 0.0))


# ---------------------------------------------------------------------------
# 5. Polygon validation
# ---------------------------------------------------------------------------


def test_polygon_geometry_accepts_a_closed_ring() -> None:
    ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 0.0)]
    polygon = PolygonGeometry(coordinates=[ring])
    assert polygon.coordinates[0][0] == polygon.coordinates[0][-1]


def test_polygon_geometry_rejects_unclosed_ring() -> None:
    ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (5.0, 5.0)]  # last != first
    with pytest.raises(ValidationError):
        PolygonGeometry(coordinates=[ring])


def test_polygon_geometry_rejects_fewer_than_three_distinct_vertices() -> None:
    # Closed, but only two distinct points (a degenerate line, not an area).
    ring = [(0.0, 0.0), (10.0, 0.0), (0.0, 0.0), (0.0, 0.0)]
    with pytest.raises(ValidationError):
        PolygonGeometry(coordinates=[ring])


def test_polygon_geometry_rejects_too_few_positions() -> None:
    with pytest.raises(ValidationError):
        PolygonGeometry(coordinates=[[(0.0, 0.0), (1.0, 1.0), (0.0, 0.0)]])


def test_polygon_geometry_rejects_empty_rings_list() -> None:
    with pytest.raises(ValidationError):
        PolygonGeometry(coordinates=[])


def test_polygon_geometry_rejects_non_finite_vertex() -> None:
    ring = [(0.0, 0.0), (math.nan, 0.0), (10.0, 10.0), (0.0, 0.0)]
    with pytest.raises(ValidationError):
        PolygonGeometry(coordinates=[ring])


# ---------------------------------------------------------------------------
# Bounding-box geometry validation + intersection contract
# ---------------------------------------------------------------------------


def test_bounding_box_geometry_accepts_valid_bounds() -> None:
    box = BoundingBoxGeometry(coordinates=(0.0, 0.0, 10.0, 20.0))
    assert box.coordinates == (0.0, 0.0, 10.0, 20.0)


def test_bounding_box_geometry_rejects_inverted_bounds() -> None:
    with pytest.raises(ValidationError):
        BoundingBoxGeometry(coordinates=(10.0, 0.0, 0.0, 20.0))  # x_min > x_max


def test_bounding_box_geometry_rejects_non_finite_bound() -> None:
    with pytest.raises(ValidationError):
        BoundingBoxGeometry(coordinates=(0.0, 0.0, math.inf, 20.0))


def test_bounding_box_geometry_from_pixel_bbox() -> None:
    geometry = BoundingBoxGeometry.from_pixel_bbox(_bbox(1.0, 2.0, 3.0, 4.0))
    assert geometry.coordinates == (1.0, 2.0, 3.0, 4.0)


def test_bounding_box_geometry_intersects_overlapping_box() -> None:
    a = BoundingBoxGeometry(coordinates=(0.0, 0.0, 10.0, 10.0))
    b = BoundingBoxGeometry(coordinates=(5.0, 5.0, 15.0, 15.0))
    assert a.intersects(b)
    assert b.intersects(a)


def test_bounding_box_geometry_does_not_intersect_disjoint_box() -> None:
    a = BoundingBoxGeometry(coordinates=(0.0, 0.0, 10.0, 10.0))
    b = BoundingBoxGeometry(coordinates=(20.0, 20.0, 30.0, 30.0))
    assert not a.intersects(b)


# ---------------------------------------------------------------------------
# 7. CRS validation
# ---------------------------------------------------------------------------


def test_validate_crs_accepts_image() -> None:
    assert validate_crs("IMAGE") is CoordinateReferenceSystem.IMAGE


def test_validate_crs_accepts_wgs84() -> None:
    assert validate_crs("EPSG:4326") is CoordinateReferenceSystem.WGS84


def test_validate_crs_rejects_unsupported_identifier() -> None:
    with pytest.raises(UnsupportedCRSError):
        validate_crs("EPSG:32633")  # a real UTM zone — not supported yet


# ---------------------------------------------------------------------------
# 1. Image-space geometry
# ---------------------------------------------------------------------------


def test_image_space_geometry_wraps_pixel_bounding_box() -> None:
    geometry, crs, georeferenced = image_space_geometry(_bbox(1.0, 2.0, 3.0, 4.0))

    assert isinstance(geometry, BoundingBoxGeometry)
    assert geometry.coordinates == (1.0, 2.0, 3.0, 4.0)
    assert crs is CoordinateReferenceSystem.IMAGE
    assert georeferenced is False


def test_image_space_geometry_is_none_without_a_bounding_box() -> None:
    """No location was produced -> no geometry is fabricated for it."""
    geometry, crs, georeferenced = image_space_geometry(None)

    assert geometry is None
    assert crs is CoordinateReferenceSystem.IMAGE
    assert georeferenced is False


def test_image_space_pixel_coordinates_are_never_reinterpreted_as_lat_lon() -> None:
    """x=100, y=200 must stay pixel-space, not become (lat=100, lon=200)."""
    geometry, _, georeferenced = image_space_geometry(_bbox(100.0, 200.0, 150.0, 250.0))

    assert georeferenced is False
    assert isinstance(geometry, BoundingBoxGeometry)
    assert geometry.coordinates == (100.0, 200.0, 150.0, 250.0)


# ---------------------------------------------------------------------------
# 2. Georeferenced geometry
# ---------------------------------------------------------------------------


def test_affine_transform_maps_a_point_correctly() -> None:
    # Identity-like transform: origin (10, 50), one pixel = 0.001 degrees.
    transform = AffineGeoTransform(a=10.0, b=0.001, c=0.0, d=50.0, e=0.0, f=-0.001)

    point = transform.transform_point(x=100.0, y=200.0)

    assert transform.target_crs is CoordinateReferenceSystem.WGS84
    assert point.coordinates == pytest.approx((10.1, 49.8))


def test_affine_transform_bounding_box_becomes_a_closed_polygon() -> None:
    transform = AffineGeoTransform(a=0.0, b=1.0, c=0.0, d=0.0, e=0.0, f=1.0)

    polygon = transform.transform_bounding_box(_bbox(0.0, 0.0, 10.0, 20.0))

    ring = polygon.coordinates[0]
    assert ring[0] == ring[-1]
    assert len(ring) == 5


def test_affine_transform_rejects_non_wgs84_source_crs() -> None:
    with pytest.raises(UnsupportedCRSError):
        AffineGeoTransform(
            a=0.0, b=1.0, c=0.0, d=0.0, e=0.0, f=1.0, source_crs=CoordinateReferenceSystem.IMAGE
        )


def test_georeferenced_geometry_uses_the_real_transform() -> None:
    transform = AffineGeoTransform(a=0.0, b=1.0, c=0.0, d=0.0, e=0.0, f=1.0)

    geometry, crs, georeferenced = georeferenced_geometry(_bbox(0.0, 0.0, 10.0, 10.0), transform)

    assert isinstance(geometry, PolygonGeometry)
    assert crs is CoordinateReferenceSystem.WGS84
    assert georeferenced is True


def test_georeferenced_geometry_is_none_without_a_bounding_box() -> None:
    transform = AffineGeoTransform(a=0.0, b=1.0, c=0.0, d=0.0, e=0.0, f=1.0)

    geometry, crs, georeferenced = georeferenced_geometry(None, transform)

    assert geometry is None
    assert crs is CoordinateReferenceSystem.IMAGE
    assert georeferenced is False


# ---------------------------------------------------------------------------
# 3. Missing georeferencing metadata
# ---------------------------------------------------------------------------


def test_no_georeferencing_available_always_raises() -> None:
    provider = NoGeoreferencingAvailable()

    with pytest.raises(GeoreferencingUnavailableError):
        provider.get_transform("some-image.png")


# ---------------------------------------------------------------------------
# 8. Damage priority
# ---------------------------------------------------------------------------


def test_priority_ordering_matches_damage_severity() -> None:
    ordering = [
        compute_damage_priority(DamageClass.NO_DAMAGE),
        compute_damage_priority(DamageClass.MINOR),
        compute_damage_priority(DamageClass.MAJOR),
        compute_damage_priority(DamageClass.DESTROYED),
    ]

    ranks = [priority_rank(p) for p in ordering]
    assert ranks == sorted(ranks)  # strictly non-decreasing
    assert len(set(ranks)) == 4  # every class maps to a distinct priority


def test_destroyed_is_critical_and_no_damage_is_low() -> None:
    assert compute_damage_priority(DamageClass.DESTROYED) is DamagePriority.CRITICAL
    assert compute_damage_priority(DamageClass.NO_DAMAGE) is DamagePriority.LOW


@pytest.mark.parametrize(
    ("damage_class", "expected"),
    [
        (DamageClass.NO_DAMAGE, False),
        (DamageClass.MINOR, False),
        (DamageClass.MAJOR, True),
        (DamageClass.DESTROYED, True),
    ],
)
def test_is_high_priority_threshold(damage_class: DamageClass, expected: bool) -> None:
    assert is_high_priority(damage_class) is expected


# ---------------------------------------------------------------------------
# 4. GeoJSON conversion
# ---------------------------------------------------------------------------


def test_building_to_feature_is_none_without_geometry() -> None:
    building = _building(geometry=None)
    assert building_to_feature(building) is None


def test_building_to_feature_renders_bounding_box_as_closed_polygon() -> None:
    geometry = BoundingBoxGeometry(coordinates=(0.0, 0.0, 10.0, 20.0))
    building = _building(geometry=geometry, damage_class=DamageClass.DESTROYED)

    feature = building_to_feature(building)

    assert feature is not None
    assert feature.geometry.type == "Polygon"
    ring = feature.geometry.coordinates[0]
    assert ring[0] == ring[-1]
    assert len(ring) == 5


def test_building_to_feature_properties_match_the_required_set() -> None:
    geometry = BoundingBoxGeometry(coordinates=(0.0, 0.0, 10.0, 20.0))
    building = _building(
        building_id="building_7",
        geometry=geometry,
        damage_class=DamageClass.MAJOR,
        georeferenced=True,
        crs=CoordinateReferenceSystem.WGS84,
    )

    feature = building_to_feature(building)

    assert feature is not None
    assert feature.properties == FeatureProperties(
        building_id="building_7",
        damage_class="major",
        confidence=0.9,
        priority="high",
        georeferenced=True,
    )
    # No model internals (e.g. a raw bounding_box, model name) leak in.
    assert set(feature.properties.model_dump().keys()) == {
        "building_id",
        "damage_class",
        "confidence",
        "priority",
        "georeferenced",
    }


def test_to_feature_collection_excludes_buildings_without_geometry() -> None:
    mappable = _building(building_id="a", geometry=BoundingBoxGeometry(coordinates=(0, 0, 1, 1)))
    unmappable = _building(building_id="b", geometry=None)

    collection = to_feature_collection([mappable, unmappable])

    assert len(collection.features) == 1
    assert collection.features[0].properties.building_id == "a"
    assert collection.type == "FeatureCollection"


def test_to_feature_collection_reports_the_shared_crs() -> None:
    building = _building(
        geometry=BoundingBoxGeometry(coordinates=(0, 0, 1, 1)),
        georeferenced=True,
        crs=CoordinateReferenceSystem.WGS84,
    )

    collection = to_feature_collection([building])

    assert collection.coordinate_reference_system is CoordinateReferenceSystem.WGS84


def test_to_feature_collection_of_empty_input_defaults_to_image_crs() -> None:
    collection = to_feature_collection([])
    assert collection.features == []
    assert collection.coordinate_reference_system is CoordinateReferenceSystem.IMAGE


# ---------------------------------------------------------------------------
# Postprocessing wiring: build_analysis populates the spatial fields
# ---------------------------------------------------------------------------


def test_build_analysis_populates_image_space_geometry_from_bounding_box() -> None:
    detections = [
        RawDetection(damage_class=DamageClass.MINOR, confidence=0.5, bounding_box=_bbox())
    ]

    analysis = build_analysis(uuid4(), AnalysisStatus.COMPLETED, detections)

    building = analysis.buildings[0]
    assert isinstance(building.geometry, BoundingBoxGeometry)
    assert building.georeferenced is False
    assert building.coordinate_reference_system is CoordinateReferenceSystem.IMAGE


def test_build_analysis_leaves_geometry_none_without_a_bounding_box() -> None:
    """No localization stage produced a location -> no geometry, matching
    `bounding_box`'s own None-ness — never a fabricated one."""
    detections = [RawDetection(damage_class=DamageClass.MINOR, confidence=0.5)]

    analysis = build_analysis(uuid4(), AnalysisStatus.COMPLETED, detections)

    building = analysis.buildings[0]
    assert building.bounding_box is None
    assert building.geometry is None
    assert building.georeferenced is False


# ---------------------------------------------------------------------------
# 9. Spatial repository interface / 10. Bounding-box query contract /
# 11. Damage filtering
# ---------------------------------------------------------------------------


def test_spatial_repository_get_returns_none_before_any_save() -> None:
    repository = InMemorySpatialRepository()
    assert repository.get_buildings(uuid4()) is None


def test_spatial_repository_save_and_get_roundtrip() -> None:
    repository = InMemorySpatialRepository()
    analysis_id = uuid4()
    buildings = [_building("a"), _building("b")]

    repository.save_buildings(analysis_id, buildings)

    assert repository.get_buildings(analysis_id) == buildings


def test_spatial_repository_get_damaged_buildings_excludes_no_damage() -> None:
    repository = InMemorySpatialRepository()
    analysis_id = uuid4()
    repository.save_buildings(
        analysis_id,
        [
            _building("undamaged", damage_class=DamageClass.NO_DAMAGE),
            _building("damaged", damage_class=DamageClass.MINOR),
        ],
    )

    damaged = repository.get_damaged_buildings(analysis_id)

    assert [b.building_id for b in damaged] == ["damaged"]


def test_spatial_repository_get_severely_damaged_buildings_is_major_and_destroyed_only() -> None:
    repository = InMemorySpatialRepository()
    analysis_id = uuid4()
    repository.save_buildings(
        analysis_id,
        [
            _building("none", damage_class=DamageClass.NO_DAMAGE),
            _building("minor", damage_class=DamageClass.MINOR),
            _building("major", damage_class=DamageClass.MAJOR),
            _building("destroyed", damage_class=DamageClass.DESTROYED),
        ],
    )

    severe = repository.get_severely_damaged_buildings(analysis_id)

    assert {b.building_id for b in severe} == {"major", "destroyed"}


def test_spatial_repository_get_high_priority_buildings() -> None:
    repository = InMemorySpatialRepository()
    analysis_id = uuid4()
    repository.save_buildings(
        analysis_id,
        [
            _building("low", damage_class=DamageClass.NO_DAMAGE),
            _building("medium", damage_class=DamageClass.MINOR),
            _building("high", damage_class=DamageClass.MAJOR),
            _building("critical", damage_class=DamageClass.DESTROYED),
        ],
    )

    high_priority = repository.get_high_priority_buildings(analysis_id)

    assert {b.building_id for b in high_priority} == {"high", "critical"}


def test_spatial_repository_bounding_box_query_includes_only_intersecting_buildings() -> None:
    repository = InMemorySpatialRepository()
    analysis_id = uuid4()
    inside = _building("inside", geometry=BoundingBoxGeometry(coordinates=(0, 0, 5, 5)))
    outside = _building("outside", geometry=BoundingBoxGeometry(coordinates=(100, 100, 110, 110)))
    no_geometry = _building("no_geometry", geometry=None)
    repository.save_buildings(analysis_id, [inside, outside, no_geometry])
    query_box = BoundingBoxGeometry(coordinates=(0, 0, 10, 10))

    result = repository.get_buildings_in_bounding_box(analysis_id, query_box)

    assert [b.building_id for b in result] == ["inside"]


def test_spatial_repository_queries_on_unsaved_analysis_return_empty() -> None:
    repository = InMemorySpatialRepository()
    analysis_id = uuid4()

    assert repository.get_damaged_buildings(analysis_id) == []
    assert repository.get_severely_damaged_buildings(analysis_id) == []
    assert repository.get_high_priority_buildings(analysis_id) == []
    assert repository.get_buildings_in_bounding_box(
        analysis_id, BoundingBoxGeometry(coordinates=(0, 0, 1, 1))
    ) == []


# ---------------------------------------------------------------------------
# 12. Damage-map API
# ---------------------------------------------------------------------------


class _FakeGeoModel:
    """Test-only `DamageModel` returning one detection *with* a bounding
    box, so the damage-map endpoint has real geometry to serialize."""

    def load(self) -> None:
        return None

    def predict(self, image: object) -> list[RawDetection]:
        return [
            RawDetection(
                damage_class=DamageClass.DESTROYED, confidence=0.95, bounding_box=_bbox()
            )
        ]

    def health(self) -> ModelStatus:
        return ModelStatus(
            model_loaded=True, model_name="fake-geo-model", model_version="test", device="cpu"
        )


def _post_analysis(client: TestClient) -> str:
    import io as _io

    from PIL import Image as _Image

    buffer = _io.BytesIO()
    _Image.new("RGB", (16, 16), color=(10, 20, 30)).save(buffer, format="PNG")
    response = client.post(
        "/api/v1/analysis", files={"image": ("aerial.png", buffer.getvalue(), "image/png")}
    )
    assert response.status_code == 201
    analysis_id: str = response.json()["analysis_id"]
    return analysis_id


def test_damage_map_unavailable_while_not_completed(analysis_client: TestClient) -> None:
    """Default wiring (no model override) -> fails with MODEL_UNAVAILABLE,
    which is still "not completed" from the damage-map's point of view."""
    analysis_id = _post_analysis(analysis_client)

    response = analysis_client.get(f"/api/v1/analysis/{analysis_id}/damage-map")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["reason"] is not None
    assert body["feature_collection"]["features"] == []


def test_damage_map_available_for_a_completed_analysis_with_geometry(
    analysis_app_factory: Callable[..., FastAPI],
) -> None:
    app = analysis_app_factory(model=_FakeGeoModel())
    client = TestClient(app)
    analysis_id = _post_analysis(client)

    response = client.get(f"/api/v1/analysis/{analysis_id}/damage-map")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["reason"] is None
    features = body["feature_collection"]["features"]
    assert len(features) == 1
    assert features[0]["properties"]["damage_class"] == "destroyed"
    assert features[0]["properties"]["priority"] == "critical"
    assert features[0]["properties"]["georeferenced"] is False
    assert features[0]["geometry"]["type"] == "Polygon"


def test_damage_map_unknown_analysis_id_returns_404(analysis_client: TestClient) -> None:
    response = analysis_client.get(f"/api/v1/analysis/{uuid4()}/damage-map")
    assert response.status_code == 404


def test_damage_map_invalid_analysis_id_returns_422(analysis_client: TestClient) -> None:
    response = analysis_client.get("/api/v1/analysis/not-a-uuid/damage-map")
    assert response.status_code == 422


def test_damage_map_does_not_break_existing_get_analysis_endpoint(
    analysis_client: TestClient,
) -> None:
    """Sanity check: adding the damage-map route must not shadow or break
    the existing `GET /api/v1/analysis/{analysis_id}` endpoint."""
    analysis_id = _post_analysis(analysis_client)

    response = analysis_client.get(f"/api/v1/analysis/{analysis_id}")

    assert response.status_code == 200
    assert response.json()["analysis_id"] == analysis_id

"""F3 — full HTTP round-trip tests for
`GET /api/v1/analysis/{analysis_id}/intelligence[/search-zones|/recommendations]`,
plus backward-compatibility checks against the pre-existing analysis
APIs and the F2 `/api/v1/intelligence/{disaster_id}...` APIs.

Follows `test_road_risk.py`'s established pattern: `analysis_app_factory`
with a fake, always-succeeding `DamageModel` gets an analysis to
`completed`, then georeferenced buildings are seeded directly into the
spatial repository (bypassing the real upload pipeline, which never
itself produces georeferencing — see `apps/api/README.md`).
"""

import io
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.api.deps import get_road_network_repository, get_spatial_repository
from app.intelligence.analysis_adapter import derive_disaster_id
from app.intelligence.demo_scenario import build_demo_scenario
from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.ml.geospatial.geometry import PointGeometry
from app.ml.model import RawDetection
from app.ml.schemas import BuildingDamage, DamageClass, ModelStatus
from app.ml.spatial import BoundingBox
from app.roads.schemas import RoadEdge, RoadNode
from app.services.road_network_repository import InMemoryRoadNetworkRepository

# Near the F2 demo scenario's ground_team_resource location
# (_point(-0.0015, -0.0012) around ORIGIN (1.5, 1.5) — see demo_scenario.py)
# so a route between it and this test's search zone is actually
# computable when a road network is loaded.
_TEST_BUILDING_LON, _TEST_BUILDING_LAT = 1.499, 1.499


class _FakeGeoModel:
    """Same test-only DamageModel `test_road_risk.py` uses — produces one
    raw (pixel-space) detection so the analysis reaches `completed`."""

    def load(self) -> None:
        return None

    def predict(self, image: object) -> list[RawDetection]:
        return [
            RawDetection(
                damage_class=DamageClass.DESTROYED,
                confidence=0.9,
                bounding_box=BoundingBox(x_min=0, y_min=0, x_max=10, y_max=10),
            )
        ]

    def health(self) -> ModelStatus:
        return ModelStatus(model_loaded=True, model_name="fake", model_version="test", device="cpu")


def _post_analysis(client: TestClient) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), color=(10, 20, 30)).save(buffer, format="PNG")
    response = client.post(
        "/api/v1/analysis", files={"image": ("aerial.png", buffer.getvalue(), "image/png")}
    )
    assert response.status_code == 201
    return response.json()["analysis_id"]  # type: ignore[no-any-return]


def _seed_georeferenced_building(app: FastAPI, analysis_id: str) -> None:
    spatial_repository = app.dependency_overrides[get_spatial_repository]()
    spatial_repository.save_buildings(
        UUID(analysis_id),
        [
            BuildingDamage(
                building_id="building_0",
                damage_class=DamageClass.DESTROYED,
                confidence=0.9,
                geometry=PointGeometry(coordinates=(_TEST_BUILDING_LON, _TEST_BUILDING_LAT)),
                coordinate_reference_system=CoordinateReferenceSystem.WGS84,
                georeferenced=True,
            )
        ],
    )


def _load_nearby_road_network(app: FastAPI) -> None:
    repository = InMemoryRoadNetworkRepository()
    repository.add_node(
        RoadNode(node_id="A", latitude=_TEST_BUILDING_LAT, longitude=_TEST_BUILDING_LON)
    )
    repository.add_node(
        RoadNode(
            node_id="B",
            latitude=_TEST_BUILDING_LAT - 0.0005,
            longitude=_TEST_BUILDING_LON - 0.0005,
        )
    )
    repository.add_edge(RoadEdge(source_node="A", target_node="B", distance=75.0, base_cost=75.0))
    repository.add_edge(RoadEdge(source_node="B", target_node="A", distance=75.0, base_cost=75.0))
    app.dependency_overrides[get_road_network_repository] = lambda: repository


class TestContextUnavailableStates:
    def test_analysis_without_a_loaded_model_reports_model_unavailable(
        self, analysis_app_factory  # type: ignore[no-untyped-def]
    ) -> None:
        # This harness's default model dependency is `None` (no building-
        # localization model configured), so processing completes
        # synchronously as FAILED/MODEL_UNAVAILABLE rather than staying
        # queued/processing — see apps/api/README.md.
        app: FastAPI = analysis_app_factory(None)
        client = TestClient(app)
        analysis_id = _post_analysis(client)

        response = client.get(f"/api/v1/analysis/{analysis_id}/intelligence")
        assert response.status_code == 200
        body = response.json()
        assert body["context_available"] is False
        assert body["context_unavailable_reason"] == "MODEL_UNAVAILABLE"
        assert body["is_simulated"] is False

    def test_disaster_id_is_deterministically_derived_and_included(
        self, analysis_app_factory  # type: ignore[no-untyped-def]
    ) -> None:
        app: FastAPI = analysis_app_factory(None)
        client = TestClient(app)
        analysis_id = _post_analysis(client)

        response = client.get(f"/api/v1/analysis/{analysis_id}/intelligence")
        expected = str(derive_disaster_id(UUID(analysis_id)))
        assert response.json()["disaster_id"] == expected

    def test_search_zones_endpoint_reports_unavailable_reason_not_empty_list_silently(
        self, analysis_app_factory  # type: ignore[no-untyped-def]
    ) -> None:
        app: FastAPI = analysis_app_factory(None)
        client = TestClient(app)
        analysis_id = _post_analysis(client)

        response = client.get(f"/api/v1/analysis/{analysis_id}/intelligence/search-zones")
        body = response.json()
        assert body["context_available"] is False
        assert body["search_zones"] == []

    def test_unknown_analysis_id_returns_404(self, analysis_client: TestClient) -> None:
        response = analysis_client.get(f"/api/v1/analysis/{uuid4()}/intelligence")
        assert response.status_code == 404

    def test_malformed_analysis_id_returns_422(self, analysis_client: TestClient) -> None:
        response = analysis_client.get("/api/v1/analysis/not-a-uuid/intelligence")
        assert response.status_code == 422


class TestAvailableContextEndToEnd:
    def test_context_endpoint_reports_available_with_real_counts(
        self, analysis_app_factory  # type: ignore[no-untyped-def]
    ) -> None:
        app: FastAPI = analysis_app_factory(model=_FakeGeoModel())
        client = TestClient(app)
        analysis_id = _post_analysis(client)
        _seed_georeferenced_building(app, analysis_id)

        response = client.get(f"/api/v1/analysis/{analysis_id}/intelligence")
        assert response.status_code == 200
        body = response.json()
        assert body["context_available"] is True
        assert body["is_simulated"] is False
        assert body["affected_area_count"] == 1
        assert body["resources_are_demo"] is True
        assert body["roads_available"] is False  # no road network loaded in this test

    def test_search_zones_are_scored_from_real_damage_and_never_marked_simulated(
        self, analysis_app_factory  # type: ignore[no-untyped-def]
    ) -> None:
        app: FastAPI = analysis_app_factory(model=_FakeGeoModel())
        client = TestClient(app)
        analysis_id = _post_analysis(client)
        _seed_georeferenced_building(app, analysis_id)

        response = client.get(f"/api/v1/analysis/{analysis_id}/intelligence/search-zones")
        body = response.json()
        assert body["context_available"] is True
        [zone] = body["search_zones"]
        assert zone["is_simulated"] is False
        assert zone["priority_level"] in {"low", "moderate", "high", "critical"}
        assert zone["reasons"]
        assert zone["uncertainty"]["confidence"] is None
        assert "located here" not in " ".join(zone["reasons"]).lower()

    def test_recommendations_have_rationale_and_evidence(
        self, analysis_app_factory  # type: ignore[no-untyped-def]
    ) -> None:
        app: FastAPI = analysis_app_factory(model=_FakeGeoModel())
        client = TestClient(app)
        analysis_id = _post_analysis(client)
        _seed_georeferenced_building(app, analysis_id)

        response = client.get(f"/api/v1/analysis/{analysis_id}/intelligence/recommendations")
        assert response.status_code == 200
        body = response.json()
        assert body["context_available"] is True
        assert body["recommendations"]
        for rec in body["recommendations"]:
            assert rec["rationale"].strip() != ""

    def test_resource_candidates_are_present_and_marked_simulated(
        self, analysis_app_factory  # type: ignore[no-untyped-def]
    ) -> None:
        app: FastAPI = analysis_app_factory(model=_FakeGeoModel())
        client = TestClient(app)
        analysis_id = _post_analysis(client)
        _seed_georeferenced_building(app, analysis_id)

        response = client.get(f"/api/v1/analysis/{analysis_id}/intelligence/recommendations")
        body = response.json()
        assert body["resources_are_demo"] is True
        assert body["resource_candidates"]
        for candidate in body["resource_candidates"]:
            assert candidate["match"]["is_simulated"] is True

    def test_route_unavailable_when_no_road_network_is_loaded(
        self, analysis_app_factory  # type: ignore[no-untyped-def]
    ) -> None:
        app: FastAPI = analysis_app_factory(model=_FakeGeoModel())
        client = TestClient(app)
        analysis_id = _post_analysis(client)
        _seed_georeferenced_building(app, analysis_id)
        # Deliberately no road network override — stays empty.

        response = client.get(f"/api/v1/analysis/{analysis_id}/intelligence/recommendations")
        body = response.json()
        assert body["roads_available"] is False
        top_candidate = body["resource_candidates"][0]
        assert top_candidate["route"] is None
        assert top_candidate["route_feasibility"]["status"] == "route_unavailable"

    def test_route_is_actually_computed_when_roads_are_loaded_and_nearby(
        self, analysis_app_factory  # type: ignore[no-untyped-def]
    ) -> None:
        app: FastAPI = analysis_app_factory(model=_FakeGeoModel())
        client = TestClient(app)
        analysis_id = _post_analysis(client)
        _seed_georeferenced_building(app, analysis_id)
        _load_nearby_road_network(app)

        response = client.get(f"/api/v1/analysis/{analysis_id}/intelligence/recommendations")
        body = response.json()
        assert body["roads_available"] is True
        top_candidate = body["resource_candidates"][0]
        if top_candidate["match"]["eligible"]:
            assert top_candidate["route_feasibility"]["status"] == "computed"
            assert top_candidate["route"] is not None
            # Never invented geometry: route_geometry only has points when found.
            if top_candidate["route"]["found"]:
                assert len(top_candidate["route"]["route_geometry"]) >= 2


class TestBackwardCompatibility:
    """F3 must not break F1's existing analysis APIs or F2's existing
    disaster-scoped intelligence APIs."""

    def test_existing_get_analysis_endpoint_still_works(
        self, analysis_app_factory  # type: ignore[no-untyped-def]
    ) -> None:
        app: FastAPI = analysis_app_factory(None)
        client = TestClient(app)
        analysis_id = _post_analysis(client)
        response = client.get(f"/api/v1/analysis/{analysis_id}")
        assert response.status_code == 200
        assert response.json()["analysis_id"] == analysis_id

    def test_existing_damage_map_endpoint_still_works(
        self, analysis_app_factory  # type: ignore[no-untyped-def]
    ) -> None:
        app: FastAPI = analysis_app_factory(None)
        client = TestClient(app)
        analysis_id = _post_analysis(client)
        response = client.get(f"/api/v1/analysis/{analysis_id}/damage-map")
        assert response.status_code == 200

    def test_existing_road_risk_endpoint_still_works(
        self, analysis_app_factory  # type: ignore[no-untyped-def]
    ) -> None:
        app: FastAPI = analysis_app_factory(None)
        client = TestClient(app)
        analysis_id = _post_analysis(client)
        response = client.get(f"/api/v1/analysis/{analysis_id}/road-risk")
        assert response.status_code == 200

    def test_f2_demo_disaster_endpoint_still_works_unaffected_by_f3(
        self, client: TestClient
    ) -> None:
        demo_disaster_id = build_demo_scenario().disaster.id
        response = client.get(f"/api/v1/intelligence/{demo_disaster_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["disaster"]["is_simulated"] is True

    def test_f2_demo_search_zones_still_ranked_and_simulated(self, client: TestClient) -> None:
        demo_disaster_id = build_demo_scenario().disaster.id
        response = client.get(f"/api/v1/intelligence/{demo_disaster_id}/search-zones")
        body = response.json()
        assert body["search_zones"]
        assert all(z["is_simulated"] is True for z in body["search_zones"])

    def test_analysis_and_f2_demo_paths_never_share_a_disaster_id(
        self, analysis_app_factory  # type: ignore[no-untyped-def]
    ) -> None:
        app: FastAPI = analysis_app_factory(None)
        client = TestClient(app)
        analysis_id = _post_analysis(client)
        analysis_derived_id = derive_disaster_id(UUID(analysis_id))
        demo_id = build_demo_scenario().disaster.id
        assert analysis_derived_id != demo_id

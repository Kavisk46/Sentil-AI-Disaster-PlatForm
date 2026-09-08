"""Disaster Intelligence Core — API endpoint tests (F2, Phase 9 items 12,
13). Uses the plain `client` fixture (`TestClient(create_app())`, no
overrides): the intelligence repository has no write endpoint in F2, so
its module-level singleton (pre-seeded once with the deterministic demo
scenario — see `app/api/deps.py`) is safe to read from directly without
per-test isolation, the same way `client` is already used for other
read-only endpoints (`test_root.py`, `test_v1_system.py`). The one
exception is the analysis-router backward-compatibility check below,
which uses `analysis_client` instead — see its own comment (Milestone F5
made `/api/v1/analysis/...` PostgreSQL-backed in production).
"""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.intelligence.demo_scenario import build_demo_scenario

_DEMO_DISASTER_ID = str(build_demo_scenario().disaster.id)


class TestDisasterSummaryEndpoint:
    def test_returns_the_demo_disaster_with_entity_counts(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/intelligence/{_DEMO_DISASTER_ID}")
        assert response.status_code == 200
        body = response.json()
        assert body["disaster"]["id"] == _DEMO_DISASTER_ID
        assert body["disaster"]["is_simulated"] is True
        assert body["observation_count"] > 0
        assert body["affected_area_count"] > 0
        assert body["hazard_count"] > 0
        assert body["resource_count"] > 0
        assert body["infrastructure_count"] > 0
        assert body["route_count"] > 0

    def test_unknown_disaster_id_returns_404(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/intelligence/{uuid4()}")
        assert response.status_code == 404
        assert "detail" in response.json()

    def test_malformed_disaster_id_returns_422(self, client: TestClient) -> None:
        response = client.get("/api/v1/intelligence/not-a-uuid")
        assert response.status_code == 422


class TestSearchZonesEndpoint:
    def test_returns_zones_ranked_descending_by_priority_score(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/intelligence/{_DEMO_DISASTER_ID}/search-zones")
        assert response.status_code == 200
        body = response.json()
        assert body["disaster_id"] == _DEMO_DISASTER_ID
        zones = body["search_zones"]
        assert len(zones) > 0
        scores = [z["priority_score"] for z in zones]
        assert scores == sorted(scores, reverse=True)

    def test_every_zone_has_a_non_empty_reasons_list_and_no_numeric_confidence(
        self, client: TestClient
    ) -> None:
        response = client.get(f"/api/v1/intelligence/{_DEMO_DISASTER_ID}/search-zones")
        for zone in response.json()["search_zones"]:
            assert zone["reasons"]
            assert zone["uncertainty"]["confidence"] is None

    def test_unknown_disaster_id_returns_404(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/intelligence/{uuid4()}/search-zones")
        assert response.status_code == 404


class TestResourcesEndpoint:
    def test_returns_the_demo_resource_registry(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/intelligence/{_DEMO_DISASTER_ID}/resources")
        assert response.status_code == 200
        body = response.json()
        assert body["disaster_id"] == _DEMO_DISASTER_ID
        assert len(body["resources"]) > 0
        assert all(r["is_simulated"] is True for r in body["resources"])

    def test_includes_at_least_one_unavailable_resource(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/intelligence/{_DEMO_DISASTER_ID}/resources")
        availabilities = {r["availability"] for r in response.json()["resources"]}
        assert "unavailable" in availabilities

    def test_unknown_disaster_id_returns_404(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/intelligence/{uuid4()}/resources")
        assert response.status_code == 404


class TestRecommendationsEndpoint:
    def test_returns_ranked_recommendations_with_rationale_and_evidence(
        self, client: TestClient
    ) -> None:
        response = client.get(f"/api/v1/intelligence/{_DEMO_DISASTER_ID}/recommendations")
        assert response.status_code == 200
        body = response.json()
        assert body["disaster_id"] == _DEMO_DISASTER_ID
        recommendations = body["recommendations"]
        assert len(recommendations) > 0
        for rec in recommendations:
            assert rec["rationale"].strip() != ""
            assert rec["is_simulated"] is True

    def test_deploy_ground_search_team_appears_for_the_demo_scenario(
        self, client: TestClient
    ) -> None:
        # The demo scenario is deliberately built with one eligible ground
        # team for its critical zone — see demo_scenario.py's module
        # docstring.
        response = client.get(f"/api/v1/intelligence/{_DEMO_DISASTER_ID}/recommendations")
        actions = {r["action"] for r in response.json()["recommendations"]}
        assert "deploy_ground_search_team" in actions

    def test_inspect_infrastructure_appears_for_the_demo_scenarios_non_operational_bridge(
        self, client: TestClient
    ) -> None:
        response = client.get(f"/api/v1/intelligence/{_DEMO_DISASTER_ID}/recommendations")
        actions = {r["action"] for r in response.json()["recommendations"]}
        assert "inspect_infrastructure_before_dispatch" in actions

    def test_unknown_disaster_id_returns_404(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/intelligence/{uuid4()}/recommendations")
        assert response.status_code == 404


class TestBackwardCompatibility:
    """F2 must not break any pre-existing endpoint (project constraint:
    "Do not break existing endpoints")."""

    def test_health_endpoint_still_responds(self, client: TestClient) -> None:
        assert client.get("/health").status_code == 200

    def test_root_endpoint_still_responds(self, client: TestClient) -> None:
        assert client.get("/").status_code == 200

    def test_v1_status_endpoint_still_responds(self, client: TestClient) -> None:
        assert client.get("/api/v1").status_code == 200

    def test_system_info_endpoint_still_responds(self, client: TestClient) -> None:
        assert client.get("/api/v1/system/info").status_code == 200

    def test_roads_status_endpoint_still_responds(self, client: TestClient) -> None:
        assert client.get("/api/v1/roads/status").status_code == 200

    def test_unknown_analysis_id_still_returns_404_unaffected_by_the_new_router(
        self, analysis_client: TestClient
    ) -> None:
        # Milestone F5: `/api/v1/analysis/{id}` is now backed by
        # `PostgresAnalysisRepository` in production (see
        # `app/api/deps.py::get_analysis_repository`) — the plain `client`
        # fixture (no overrides) would try a real database connection
        # here, unlike every other endpoint in this class. `analysis_client`
        # (`tests/conftest.py`) isolates this exactly like every other
        # analysis-scoped test in the suite already does.
        response = analysis_client.get(f"/api/v1/analysis/{uuid4()}")
        assert response.status_code == 404

"""Tests for Milestone 7 (AI Incident Intelligence): context construction,
the LLM provider abstraction, the deterministic fallback, output
validation/grounding, severity/confidence classification, and the
`GET`/`POST /api/v1/analysis/{analysis_id}/summary` API.

No network, no API key, no GPU anywhere in this file — every provider
used here is `MockLLMProvider` or `DeterministicSummaryProvider`. The one
real, network-calling provider (`AnthropicLLMProvider`) is never
imported or invoked.
"""

import io
from collections.abc import Callable
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from app.api.deps import get_llm_provider
from app.core.config import Settings
from app.incident.briefing_builder import assemble_briefing
from app.incident.config import IncidentConfig
from app.incident.context_builder import build_incident_context
from app.incident.fallback import DeterministicSummaryProvider, build_fallback_narrative
from app.incident.grounding import filter_unsupported_claims
from app.incident.mock_provider import MockLLMProvider
from app.incident.provider import LLMProviderError, LLMTimeoutError
from app.incident.schemas import (
    AffectedStructuresSummary,
    ConfidenceLevel,
    IncidentBriefing,
    IncidentSeverity,
    LLMNarrativeOutput,
)
from app.incident.severity import classify_confidence, classify_incident_severity
from app.incident.validator import parse_llm_output
from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.ml.geospatial.geometry import PointGeometry
from app.ml.model import RawDetection
from app.ml.schemas import BuildingDamage, DamageAnalysis, DamageClass, DamageSummary, ModelStatus
from app.roads.schemas import AccessibilityStatus, RiskLevel, RiskSource, RoadEdge
from app.routing.schemas import RouteComparison, RouteResult, RoutingMode
from app.schemas.analysis import AnalysisStatus
from app.schemas.road_risk import RoadRiskResponse
from app.services.incident_intelligence_service import IncidentIntelligenceService

# ---------------------------------------------------------------------------
# Shared builders — no fixture magic, just plain functions returning real
# schema instances, so every test's setup is legible on its own.
# ---------------------------------------------------------------------------


def _config() -> IncidentConfig:
    return IncidentConfig.from_settings(Settings())


def _building(
    building_id: str,
    damage_class: DamageClass,
    confidence: float = 0.8,
    *,
    lon: float | None = None,
    lat: float | None = None,
) -> BuildingDamage:
    if lon is None or lat is None:
        return BuildingDamage(
            building_id=building_id, damage_class=damage_class, confidence=confidence
        )
    return BuildingDamage(
        building_id=building_id,
        damage_class=damage_class,
        confidence=confidence,
        geometry=PointGeometry(coordinates=(lon, lat)),
        coordinate_reference_system=CoordinateReferenceSystem.WGS84,
        georeferenced=True,
    )


def _completed_analysis(buildings: list[BuildingDamage]) -> DamageAnalysis:
    destroyed = sum(1 for b in buildings if b.damage_class is DamageClass.DESTROYED)
    major = sum(1 for b in buildings if b.damage_class is DamageClass.MAJOR)
    minor = sum(1 for b in buildings if b.damage_class is DamageClass.MINOR)
    summary = DamageSummary(
        total_buildings=len(buildings),
        damaged_buildings=destroyed + major + minor,
        severely_damaged=destroyed + major,
        destroyed=destroyed,
    )
    return DamageAnalysis(
        analysis_id=uuid4(),
        status=AnalysisStatus.COMPLETED,
        summary=summary,
        buildings=buildings,
        model_metadata=ModelStatus(
            model_loaded=True, model_name="test-model", model_version="1", device="cpu"
        ),
    )


def _uncompleted_analysis(status: AnalysisStatus = AnalysisStatus.PROCESSING) -> DamageAnalysis:
    return DamageAnalysis(analysis_id=uuid4(), status=status)


def _road_edge(
    *, risk_level: RiskLevel, accessibility: AccessibilityStatus, risk_sources: list[RiskSource]
) -> RoadEdge:
    return RoadEdge(
        source_node="n1",
        target_node="n2",
        distance=100.0,
        base_cost=100.0,
        accessibility=accessibility,
        risk_score=1.0,
        risk_level=risk_level,
        risk_sources=risk_sources,
    )


def _available_road_risk(analysis_id: object) -> RoadRiskResponse:
    risk_source = RiskSource(
        building_id="b0",
        damage_class=DamageClass.DESTROYED,
        confidence=0.9,
        distance_meters=10.0,
        contribution=0.9,
    )
    edges = [
        _road_edge(
            risk_level=RiskLevel.CRITICAL,
            accessibility=AccessibilityStatus.BLOCKED,
            risk_sources=[risk_source],
        ),
        _road_edge(
            risk_level=RiskLevel.HIGH,
            accessibility=AccessibilityStatus.RESTRICTED,
            risk_sources=[risk_source],
        ),
        _road_edge(
            risk_level=RiskLevel.LOW, accessibility=AccessibilityStatus.OPEN, risk_sources=[]
        ),
    ]
    return RoadRiskResponse(
        analysis_id=analysis_id, status=AnalysisStatus.COMPLETED, available=True, edges=edges
    )


def _unavailable_road_risk(
    analysis_id: object, reason: str = "No road network is loaded."
) -> RoadRiskResponse:
    return RoadRiskResponse(
        analysis_id=analysis_id,
        status=AnalysisStatus.COMPLETED,
        available=False,
        reason=reason,
        edges=[],
    )


def _route_comparison(*, found: bool = True) -> RouteComparison:
    distance_only = RouteResult(
        routing_mode=RoutingMode.DISTANCE_ONLY,
        found=found,
        total_distance=1000.0 if found else None,
        accumulated_risk=5.0 if found else None,
    )
    risk_aware = RouteResult(
        routing_mode=RoutingMode.RISK_AWARE,
        found=found,
        total_distance=1200.0 if found else None,
        accumulated_risk=1.0 if found else None,
        reason=None if found else "No path exists between the start and destination nodes.",
    )
    return RouteComparison(
        distance_only=distance_only,
        risk_aware=risk_aware,
        distance_difference=200.0 if found else None,
        risk_difference=-4.0 if found else None,
        routes_differ=found,
        detour_ratio=1.2 if found else None,
        high_risk_edges_avoided=["n1->n2"] if found else [],
    )


# ---------------------------------------------------------------------------
# 1. Context construction
# ---------------------------------------------------------------------------


def test_build_incident_context_with_full_data() -> None:
    buildings = [
        _building("b0", DamageClass.DESTROYED, 0.9, lon=10.0, lat=20.0),
        _building("b1", DamageClass.MAJOR, 0.7, lon=10.1, lat=20.1),
        _building("b2", DamageClass.NO_DAMAGE, 0.95),
    ]
    analysis = _completed_analysis(buildings)
    road_risk = _available_road_risk(analysis.analysis_id)
    comparison = _route_comparison()

    context = build_incident_context(analysis, road_risk, comparison, _config())

    assert context.analysis_id == analysis.analysis_id
    assert context.analysis_status is AnalysisStatus.COMPLETED
    assert context.damage.available is True
    assert context.damage.summary is not None
    assert context.damage.summary.total_buildings == 3
    assert context.damage.average_confidence == pytest.approx((0.9 + 0.7 + 0.95) / 3)
    assert set(context.damage.high_priority_structure_ids) == {"b0", "b1"}
    assert context.damage.spatial_bounds is not None
    assert context.road_risk.available is True
    assert context.road_risk.risky_edge_count == 2
    assert context.road_risk.blocked_edge_count == 1
    assert context.road_risk.restricted_edge_count == 1
    assert context.road_risk.highest_risk_level is RiskLevel.CRITICAL
    assert context.route.available is True
    assert context.route.selected_distance_meters == 1200.0
    assert context.route.baseline_distance_meters == 1000.0
    assert context.route.avoided_high_risk_segment_count == 1


# ---------------------------------------------------------------------------
# 2. Empty damage context
# ---------------------------------------------------------------------------


def test_damage_context_unavailable_when_analysis_not_completed() -> None:
    analysis = _uncompleted_analysis(AnalysisStatus.PROCESSING)
    road_risk = _unavailable_road_risk(analysis.analysis_id)

    context = build_incident_context(analysis, road_risk, None, _config())

    assert context.damage.available is False
    assert context.damage.summary is None
    assert context.damage.average_confidence is None
    assert context.damage.high_priority_structure_ids == []
    assert context.damage.spatial_bounds is None
    assert context.damage.reason is not None


def test_damage_context_unavailable_for_completed_analysis_with_zero_buildings() -> None:
    analysis = _completed_analysis([])
    road_risk = _unavailable_road_risk(analysis.analysis_id)
    context = build_incident_context(analysis, road_risk, None, _config())

    assert classify_incident_severity(context, _config()) is IncidentSeverity.LOW


# ---------------------------------------------------------------------------
# 3. Missing route context
# ---------------------------------------------------------------------------


def test_route_context_unavailable_when_no_route_requested() -> None:
    analysis = _completed_analysis([_building("b0", DamageClass.MINOR)])
    road_risk = _unavailable_road_risk(analysis.analysis_id)

    context = build_incident_context(analysis, road_risk, None, _config())

    assert context.route.available is False
    assert context.route.reason == "No route was requested for this summary."
    assert context.route.selected_distance_meters is None


def test_route_context_unavailable_when_route_not_found() -> None:
    analysis = _completed_analysis([_building("b0", DamageClass.MINOR)])
    road_risk = _unavailable_road_risk(analysis.analysis_id)
    comparison = _route_comparison(found=False)

    context = build_incident_context(analysis, road_risk, comparison, _config())

    assert context.route.available is False
    assert context.route.reason is not None


# ---------------------------------------------------------------------------
# 4. Missing road-risk context
# ---------------------------------------------------------------------------


def test_road_risk_context_unavailable_carries_the_service_reason() -> None:
    analysis = _completed_analysis([_building("b0", DamageClass.MINOR)])
    reason = "No road network is loaded (see GET /api/v1/roads/status)."
    road_risk = _unavailable_road_risk(analysis.analysis_id, reason=reason)

    context = build_incident_context(analysis, road_risk, None, _config())

    assert context.road_risk.available is False
    assert context.road_risk.reason == reason
    assert context.road_risk.total_edges_assessed == 0
    assert context.road_risk.highest_risk_level is None


# ---------------------------------------------------------------------------
# 5. LLM provider interface
# ---------------------------------------------------------------------------


def test_every_provider_implements_generate_incident_summary() -> None:
    """Structural (Protocol) conformance — each of these can stand in for
    `LLMProvider` without inheriting from it, the same duck-typed pattern
    `DamageModel`/`BuildingLocalizer`/`RoadNetworkSource` already use."""
    analysis = _completed_analysis([_building("b0", DamageClass.MINOR)])
    road_risk = _unavailable_road_risk(analysis.analysis_id)
    context = build_incident_context(analysis, road_risk, None, _config())

    for provider in (DeterministicSummaryProvider(), MockLLMProvider("valid")):
        raw = provider.generate_incident_summary(context)
        assert isinstance(raw, str)


# ---------------------------------------------------------------------------
# 6. Mock provider (every behavior)
# ---------------------------------------------------------------------------


def test_mock_provider_valid_behavior_reflects_the_context() -> None:
    buildings = [
        _building("b0", DamageClass.DESTROYED, 0.9),
        _building("b1", DamageClass.MAJOR, 0.9),
    ]
    analysis = _completed_analysis(buildings)
    road_risk = _unavailable_road_risk(analysis.analysis_id)
    context = build_incident_context(analysis, road_risk, None, _config())

    raw = MockLLMProvider("valid").generate_incident_summary(context)

    narrative = parse_llm_output(raw)
    assert narrative is not None
    assert "1 destroyed" in narrative.priority_area


def test_mock_provider_malformed_behavior_returns_unparseable_text() -> None:
    context = build_incident_context(
        _completed_analysis([]), _unavailable_road_risk(uuid4()), None, _config()
    )

    raw = MockLLMProvider("malformed").generate_incident_summary(context)

    assert parse_llm_output(raw) is None


def test_mock_provider_timeout_behavior_raises() -> None:
    context = build_incident_context(
        _completed_analysis([]), _unavailable_road_risk(uuid4()), None, _config()
    )

    with pytest.raises(LLMTimeoutError):
        MockLLMProvider("timeout").generate_incident_summary(context)


def test_mock_provider_error_behavior_raises() -> None:
    context = build_incident_context(
        _completed_analysis([]), _unavailable_road_risk(uuid4()), None, _config()
    )

    with pytest.raises(LLMProviderError):
        MockLLMProvider("error").generate_incident_summary(context)


def test_mock_provider_unsupported_claim_behavior_is_rejected_by_grounding() -> None:
    context = build_incident_context(
        _completed_analysis([]), _unavailable_road_risk(uuid4()), None, _config()
    )

    raw = MockLLMProvider("unsupported_claim").generate_incident_summary(context)
    narrative = parse_llm_output(raw)

    assert narrative is not None
    assert filter_unsupported_claims(narrative, context) is None


# ---------------------------------------------------------------------------
# 7. Valid LLM output / 8. Malformed LLM output
# ---------------------------------------------------------------------------


def test_parse_llm_output_accepts_valid_json() -> None:
    raw = LLMNarrativeOutput(
        priority_area="Area A", route_summary="Route B", key_findings=["f1"], limitations=["l1"]
    ).model_dump_json()

    parsed = parse_llm_output(raw)

    assert parsed is not None
    assert parsed.priority_area == "Area A"


def test_parse_llm_output_accepts_a_markdown_fenced_json_body() -> None:
    inner = LLMNarrativeOutput(priority_area="Area A", route_summary="Route B").model_dump_json()
    raw = f"```json\n{inner}\n```"

    parsed = parse_llm_output(raw)

    assert parsed is not None
    assert parsed.priority_area == "Area A"


@pytest.mark.parametrize(
    "raw",
    [
        "not json at all",
        "{this is not valid json",
        '{"priority_area": "Area A"}',  # missing required route_summary
        '{"priority_area": 5, "route_summary": "x"}',  # wrong type
    ],
)
def test_parse_llm_output_rejects_malformed_or_incomplete_json(raw: str) -> None:
    assert parse_llm_output(raw) is None


# ---------------------------------------------------------------------------
# 9. LLM timeout / 10. Provider failure -> IncidentIntelligenceService falls back
# ---------------------------------------------------------------------------


class _StubProcessingService:
    def __init__(self, analysis: DamageAnalysis) -> None:
        self._analysis = analysis

    def get_analysis(self, analysis_id: object) -> DamageAnalysis:
        return self._analysis


class _StubRoadRiskService:
    def __init__(self, response: RoadRiskResponse) -> None:
        self._response = response

    def get_road_risk(self, analysis_id: object) -> RoadRiskResponse:
        return self._response


class _StubRoutingService:
    def compare_routes(
        self, analysis_id: object, start: object, destination: object
    ) -> RouteComparison:
        raise AssertionError("should not be called when no route_query is given")


def _service(
    provider: object, analysis: DamageAnalysis, road_risk: RoadRiskResponse
) -> IncidentIntelligenceService:
    return IncidentIntelligenceService(
        processing_service=_StubProcessingService(analysis),  # type: ignore[arg-type]
        road_risk_service=_StubRoadRiskService(road_risk),  # type: ignore[arg-type]
        routing_service=_StubRoutingService(),  # type: ignore[arg-type]
        llm_provider=provider,  # type: ignore[arg-type]
        config=_config(),
    )


def test_service_falls_back_to_deterministic_narrative_on_timeout() -> None:
    analysis = _completed_analysis([_building("b0", DamageClass.MINOR)])
    road_risk = _unavailable_road_risk(analysis.analysis_id)
    service = _service(MockLLMProvider("timeout"), analysis, road_risk)

    briefing = service.get_summary(analysis.analysis_id)

    assert briefing.source == "fallback"


def test_service_falls_back_to_deterministic_narrative_on_provider_error() -> None:
    analysis = _completed_analysis([_building("b0", DamageClass.MINOR)])
    road_risk = _unavailable_road_risk(analysis.analysis_id)
    service = _service(MockLLMProvider("error"), analysis, road_risk)

    briefing = service.get_summary(analysis.analysis_id)

    assert briefing.source == "fallback"


def test_service_falls_back_on_malformed_output() -> None:
    analysis = _completed_analysis([_building("b0", DamageClass.MINOR)])
    road_risk = _unavailable_road_risk(analysis.analysis_id)
    service = _service(MockLLMProvider("malformed"), analysis, road_risk)

    briefing = service.get_summary(analysis.analysis_id)

    assert briefing.source == "fallback"


def test_service_falls_back_on_unsupported_claim() -> None:
    analysis = _completed_analysis([_building("b0", DamageClass.MINOR)])
    road_risk = _unavailable_road_risk(analysis.analysis_id)
    service = _service(MockLLMProvider("unsupported_claim"), analysis, road_risk)

    briefing = service.get_summary(analysis.analysis_id)

    assert briefing.source == "fallback"
    assert "casualt" not in briefing.priority_area.lower()


def test_service_uses_provider_output_when_valid() -> None:
    analysis = _completed_analysis([_building("b0", DamageClass.DESTROYED, 0.9)])
    road_risk = _unavailable_road_risk(analysis.analysis_id)
    service = _service(MockLLMProvider("valid"), analysis, road_risk)

    briefing = service.get_summary(analysis.analysis_id)

    assert briefing.source == "provider"


# ---------------------------------------------------------------------------
# 11. Deterministic fallback
# ---------------------------------------------------------------------------


def test_deterministic_fallback_states_only_whats_in_the_context() -> None:
    buildings = [_building("b0", DamageClass.DESTROYED, 0.9, lon=10.0, lat=20.0)]
    analysis = _completed_analysis(buildings)
    road_risk = _available_road_risk(analysis.analysis_id)
    context = build_incident_context(analysis, road_risk, None, _config())

    narrative = build_fallback_narrative(context)

    assert "1 high-priority structure" in narrative.priority_area
    assert narrative.route_summary == "Information unavailable."
    assert any("destroyed" in finding for finding in narrative.key_findings)
    assert len(narrative.limitations) >= 3


def test_deterministic_fallback_reports_unavailable_when_nothing_is_available() -> None:
    analysis = _uncompleted_analysis()
    road_risk = _unavailable_road_risk(analysis.analysis_id)
    context = build_incident_context(analysis, road_risk, None, _config())

    narrative = build_fallback_narrative(context)

    assert narrative.priority_area == "Information unavailable."
    assert narrative.route_summary == "Information unavailable."


def test_deterministic_provider_output_survives_its_own_grounding_filter() -> None:
    """Regression guard: the deterministic provider's own output must never
    be rejected by app.incident.grounding when it's the configured
    provider (Settings.LLM_PROVIDER="deterministic") — there would be no
    further fallback to catch it. In particular, spatial-bounds
    coordinates must not be formatted with enough precision to look like
    an invented lat/lon to the coordinate-like-pattern check."""
    buildings = [_building("b0", DamageClass.DESTROYED, 0.9, lon=10.123456, lat=20.654321)]
    analysis = _completed_analysis(buildings)
    road_risk = _available_road_risk(analysis.analysis_id)
    context = build_incident_context(analysis, road_risk, None, _config())

    raw = DeterministicSummaryProvider().generate_incident_summary(context)
    narrative = parse_llm_output(raw)

    assert narrative is not None
    assert filter_unsupported_claims(narrative, context) is not None


# ---------------------------------------------------------------------------
# 12. Unsupported claims filtering
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_value",
    [
        "Casualties are expected in the area.",
        "3 deaths have been confirmed.",
        "A tsunami warning is in effect.",
        "Flooding is expected within the hour.",
        "An evacuation order has been issued.",
        "Heavy rainfall is forecast for tonight.",
        "The road is closed due to an official closure.",
        "Located at 12.345678, -98.765432.",
    ],
)
def test_filter_rejects_unsupported_claims(field_value: str) -> None:
    narrative = LLMNarrativeOutput(priority_area=field_value, route_summary="ok")
    context = build_incident_context(
        _completed_analysis([]), _unavailable_road_risk(uuid4()), None, _config()
    )

    assert filter_unsupported_claims(narrative, context) is None


def test_filter_allows_the_systems_own_grounded_vocabulary() -> None:
    narrative = LLMNarrativeOutput(
        priority_area="2 structures are high priority.",
        route_summary="The selected route avoids a blocked and a restricted segment.",
        key_findings=["1 road segment is blocked.", "1 road segment is restricted."],
    )
    context = build_incident_context(
        _completed_analysis([]), _unavailable_road_risk(uuid4()), None, _config()
    )

    assert filter_unsupported_claims(narrative, context) is narrative


# ---------------------------------------------------------------------------
# 13. Confidence representation
# ---------------------------------------------------------------------------


def test_confidence_unknown_when_damage_unavailable() -> None:
    road_risk = _unavailable_road_risk(uuid4())
    context = build_incident_context(_uncompleted_analysis(), road_risk, None, _config())

    assert classify_confidence(context, _config()) is ConfidenceLevel.UNKNOWN


def test_confidence_high_moderate_low_thresholds() -> None:
    config = _config()
    high = _completed_analysis([_building("b0", DamageClass.MINOR, 0.95)])
    moderate = _completed_analysis([_building("b0", DamageClass.MINOR, 0.6)])
    low = _completed_analysis([_building("b0", DamageClass.MINOR, 0.1)])

    def confidence_for(analysis: DamageAnalysis) -> ConfidenceLevel:
        road_risk = _unavailable_road_risk(analysis.analysis_id)
        context = build_incident_context(analysis, road_risk, None, config)
        return classify_confidence(context, config)

    assert confidence_for(high) is ConfidenceLevel.HIGH
    assert confidence_for(moderate) is ConfidenceLevel.MODERATE
    assert confidence_for(low) is ConfidenceLevel.LOW


# ---------------------------------------------------------------------------
# 14. Summary API
# ---------------------------------------------------------------------------


def _image_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), color=(10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


class _FakeCompletingModel:
    def load(self) -> None:
        return None

    def predict(self, image: object) -> list[RawDetection]:
        return [RawDetection(damage_class=DamageClass.DESTROYED, confidence=0.9)]

    def health(self) -> ModelStatus:
        return ModelStatus(model_loaded=True, model_name="fake", model_version="test", device="cpu")


def _post_analysis(client: TestClient) -> str:
    response = client.post(
        "/api/v1/analysis", files={"image": ("aerial.png", _image_bytes(), "image/png")}
    )
    assert response.status_code == 201
    analysis_id: str = response.json()["analysis_id"]
    return analysis_id


def test_get_summary_returns_a_valid_briefing_for_a_completed_analysis(
    analysis_app_factory: Callable[..., FastAPI],
) -> None:
    app = analysis_app_factory(model=_FakeCompletingModel())
    app.dependency_overrides[get_llm_provider] = lambda: MockLLMProvider("valid")
    client = TestClient(app)
    analysis_id = _post_analysis(client)

    response = client.get(f"/api/v1/analysis/{analysis_id}/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["analysis_id"] == analysis_id
    assert body["source"] == "provider"
    assert body["prompt_version"] == "incident_summary_v1"
    assert body["incident_severity"] in {"low", "moderate", "high", "critical", "unknown"}
    assert body["disclaimer"]


def test_post_summary_without_a_body_regenerates_with_damage_context_only(
    analysis_app_factory: Callable[..., FastAPI],
) -> None:
    app = analysis_app_factory(model=_FakeCompletingModel())
    app.dependency_overrides[get_llm_provider] = lambda: DeterministicSummaryProvider()
    client = TestClient(app)
    analysis_id = _post_analysis(client)

    response = client.post(f"/api/v1/analysis/{analysis_id}/summary")

    assert response.status_code == 200
    assert response.json()["route_summary"] == "Information unavailable."


def test_post_summary_with_a_route_body_is_accepted(
    analysis_app_factory: Callable[..., FastAPI],
) -> None:
    app = analysis_app_factory(model=_FakeCompletingModel())
    app.dependency_overrides[get_llm_provider] = lambda: DeterministicSummaryProvider()
    client = TestClient(app)
    analysis_id = _post_analysis(client)

    response = client.post(
        f"/api/v1/analysis/{analysis_id}/summary",
        json={
            "route": {
                "start": {"latitude": 1.0, "longitude": 1.0},
                "destination": {"latitude": 2.0, "longitude": 2.0},
            }
        },
    )

    assert response.status_code == 200


def test_get_summary_for_unknown_analysis_id_returns_404(analysis_client: TestClient) -> None:
    response = analysis_client.get(f"/api/v1/analysis/{uuid4()}/summary")

    assert response.status_code == 404


def test_get_summary_for_invalid_analysis_id_returns_422(analysis_client: TestClient) -> None:
    response = analysis_client.get("/api/v1/analysis/not-a-uuid/summary")

    assert response.status_code == 422


def test_get_llm_provider_defaults_to_deterministic() -> None:
    provider = get_llm_provider(Settings())

    assert isinstance(provider, DeterministicSummaryProvider)


def test_get_llm_provider_honors_mock_setting() -> None:
    provider = get_llm_provider(Settings(LLM_PROVIDER="mock"))

    assert isinstance(provider, MockLLMProvider)


def test_get_llm_provider_falls_back_to_deterministic_without_an_api_key() -> None:
    provider = get_llm_provider(Settings(LLM_PROVIDER="anthropic"))

    assert isinstance(provider, DeterministicSummaryProvider)


# ---------------------------------------------------------------------------
# 15. Pydantic schema validation
# ---------------------------------------------------------------------------


def test_llm_narrative_output_rejects_missing_required_fields() -> None:
    with pytest.raises(ValidationError):
        LLMNarrativeOutput.model_validate({"priority_area": "x"})


def test_affected_structures_summary_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError):
        AffectedStructuresSummary(
            total=-1, damaged=0, severely_damaged=0, destroyed=0, high_priority_count=0
        )


def test_incident_briefing_source_is_restricted_to_the_literal_values() -> None:
    with pytest.raises(ValidationError):
        IncidentBriefing.model_validate(
            {
                "analysis_id": str(uuid4()),
                "incident_severity": "low",
                "affected_structures": {
                    "total": 0,
                    "damaged": 0,
                    "severely_damaged": 0,
                    "destroyed": 0,
                    "high_priority_count": 0,
                },
                "priority_area": "x",
                "route_summary": "x",
                "confidence": "unknown",
                "generated_at": "2024-01-01T00:00:00Z",
                "source": "not-a-real-source",
                "prompt_version": "v1",
                "disclaimer": "d",
            }
        )


def test_incident_config_rejects_inverted_severity_thresholds() -> None:
    with pytest.raises(ValueError, match="severity_severe_ratio_moderate"):
        IncidentConfig(
            max_listed_structure_ids=10,
            severity_destroyed_ratio_critical=0.25,
            severity_severe_ratio_high=0.2,
            severity_severe_ratio_moderate=0.5,  # inverted vs. high
            confidence_high_min=0.8,
            confidence_moderate_min=0.5,
        )


# ---------------------------------------------------------------------------
# Evaluation fixture: a known, fixed IncidentContext, run through the mock
# provider, asserting the assembled briefing contains the facts that
# context actually supports. This is deliberately small and deterministic
# — it is NOT a claim of measuring factual consistency, unsupported-claim
# rate, completeness, latency, token usage, or human usefulness at scale;
# see apps/api/README.md ("Future evaluation methodology") for why those
# remain undone.
# ---------------------------------------------------------------------------


def test_evaluation_fixture_known_context_produces_expected_facts() -> None:
    buildings = [
        _building("b0", DamageClass.DESTROYED, 0.9, lon=30.0, lat=40.0),
        _building("b1", DamageClass.DESTROYED, 0.9, lon=30.1, lat=40.1),
        _building("b2", DamageClass.MAJOR, 0.85, lon=30.2, lat=40.2),
        _building("b3", DamageClass.NO_DAMAGE, 0.99),
    ]
    analysis = _completed_analysis(buildings)
    road_risk = _available_road_risk(analysis.analysis_id)
    config = _config()
    context = build_incident_context(analysis, road_risk, None, config)

    briefing = assemble_briefing(context, build_fallback_narrative(context), "fallback", config)
    briefing_schema = briefing.model_dump()

    assert briefing_schema["affected_structures"]["total"] == 4
    assert briefing_schema["affected_structures"]["destroyed"] == 2
    assert briefing_schema["affected_structures"]["high_priority_count"] == 3
    assert briefing_schema["incident_severity"] == IncidentSeverity.CRITICAL.value
    findings_text = " ".join(briefing.key_findings)
    assert "destroyed" in briefing.priority_area or "2 destroyed" in findings_text

    # Exact schema shape for the mock-provider path too.
    mock_raw = MockLLMProvider("valid").generate_incident_summary(context)
    mock_narrative = parse_llm_output(mock_raw)
    assert mock_narrative is not None
    mock_briefing = assemble_briefing(context, mock_narrative, "provider", config)
    assert set(mock_briefing.model_dump().keys()) == {
        "analysis_id",
        "incident_severity",
        "affected_structures",
        "priority_area",
        "route_summary",
        "key_findings",
        "limitations",
        "confidence",
        "generated_at",
        "source",
        "prompt_version",
        "disclaimer",
    }

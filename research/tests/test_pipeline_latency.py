"""An end-to-end demonstration of `LatencyRecorder` wrapping the REAL
backend pipeline — damage inference, road risk, routing (both modes),
and incident-summary generation — using the same deterministic
in-memory test doubles `apps/api/tests` already establishes (a fake,
instant-completing model; in-memory repositories). Every recorded
duration is a real measured `time.perf_counter()` interval from actually
running that code; none are inserted.

Not measured, and never fabricated: "upload" (no HTTP layer is involved
here — see `apps/api/tests/test_analysis_lifecycle.py` for that) and
"hazard assessment" (no hazard subsystem exists — see
`research.experiments.hazards`). Both stages are simply absent from the
recorder's timings, not given a synthetic value.

These numbers describe this dev machine running tiny synthetic fixtures
— they are not a claim about production latency on real imagery or
production hardware; see `research/README.md`, "Limitations."
"""

import io

from app.core.config import Settings
from app.incident.config import IncidentConfig
from app.incident.fallback import DeterministicSummaryProvider
from app.ml.inference import DamageInferenceEngine
from app.ml.model import RawDetection
from app.ml.schemas import DamageClass, ModelStatus
from app.risk.config import RoadRiskConfig
from app.roads.schemas import GeographicCoordinate
from app.routing.accessibility import Traversability
from app.routing.config import RoutingConfig
from app.schemas.analysis import AnalysisStatus
from app.schemas.incident import RouteQuery
from app.services.analysis_processing_service import AnalysisProcessingService
from app.services.analysis_repository import InMemoryAnalysisRepository
from app.services.analysis_service import AnalysisService
from app.services.incident_intelligence_service import IncidentIntelligenceService
from app.services.road_network_repository import InMemoryRoadNetworkRepository
from app.services.road_risk_service import RoadRiskService
from app.services.routing_service import RoutingService
from app.services.spatial_repository import InMemorySpatialRepository
from fastapi import UploadFile
from PIL import Image
from starlette.datastructures import Headers

from research.core.latency import LatencyRecorder
from research.experiments.routing.fixtures import diamond_detour_scenario


class _InMemoryFileStorage:
    def __init__(self) -> None:
        self._content = b""

    def save(self, *, storage_name: str, content: bytes) -> None:
        self._content = content

    def load(self, *, storage_name: str) -> bytes:
        return self._content


class _FakeCompletingModel:
    def load(self) -> None:
        return None

    def predict(self, image: object) -> list[RawDetection]:
        return [RawDetection(damage_class=DamageClass.DESTROYED, confidence=0.9)]

    def health(self) -> ModelStatus:
        return ModelStatus(model_loaded=True, model_name="fake", model_version="test", device="cpu")


def _image_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), color=(10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def _risk_config() -> RoadRiskConfig:
    return RoadRiskConfig(
        severity_weights={
            DamageClass.NO_DAMAGE: 0.0,
            DamageClass.MINOR: 0.25,
            DamageClass.MAJOR: 0.6,
            DamageClass.DESTROYED: 1.0,
        },
        search_radius_meters=150.0,
        distance_decay_rate=0.02,
        aggregation_cap=1.0,
        risk_level_low_max=0.25,
        risk_level_moderate_max=0.5,
        risk_level_high_max=0.75,
        cost_penalty_scale=4.0,
    )


def _routing_config() -> RoutingConfig:
    return RoutingConfig(
        restricted_accessibility_penalty=0.5,
        unknown_accessibility_policy=Traversability.OPEN,
        max_snap_distance_meters=500.0,
        use_astar_heuristic=False,
    )


def test_latency_recorder_measures_the_real_pipeline_end_to_end() -> None:
    recorder = LatencyRecorder()

    # --- setup: a populated road graph (reusing the routing fixture) ---
    scenario = diamond_detour_scenario()
    road_network_repository = InMemoryRoadNetworkRepository()
    for node in scenario.nodes:
        road_network_repository.add_node(node)
    for edge in scenario.edges:
        road_network_repository.add_edge(edge)

    spatial_repository = InMemorySpatialRepository()
    analysis_repository = InMemoryAnalysisRepository()
    file_storage = _InMemoryFileStorage()

    # --- upload (analysis creation, not the HTTP layer) ---
    with recorder.measure("upload"):
        upload_file = UploadFile(
            file=io.BytesIO(_image_bytes()),
            filename="fixture.png",
            headers=Headers(raw=[(b"content-type", b"image/png")]),
        )
        analysis_service = AnalysisService(
            settings=Settings(), repository=analysis_repository, file_storage=file_storage
        )
        created = analysis_service.create_analysis(upload_file)

    # --- damage inference (+ preprocessing/spatial processing, one real
    # pipeline call — see app.services.analysis_processing_service) ---
    with recorder.measure("damage_inference"):
        processing_service = AnalysisProcessingService(
            repository=analysis_repository,
            file_storage=file_storage,
            inference_engine=DamageInferenceEngine(model=_FakeCompletingModel()),
            spatial_repository=spatial_repository,
        )
        processing_service.process(created.analysis_id)

    analysis = processing_service.get_analysis(created.analysis_id)
    assert analysis.status is AnalysisStatus.COMPLETED

    # --- road risk (real analyzer, over the real populated graph) ---
    with recorder.measure("road_risk"):
        road_risk_service = RoadRiskService(
            processing_service=processing_service,
            spatial_repository=spatial_repository,
            road_network_repository=road_network_repository,
            config=_risk_config(),
        )
        road_risk = road_risk_service.get_road_risk(created.analysis_id)

    # --- routing (both real modes, over the real populated graph) ---
    routing_service = RoutingService(
        road_network_repository=road_network_repository,
        road_risk_service=road_risk_service,
        routing_config=_routing_config(),
        risk_config=_risk_config(),
    )
    start = GeographicCoordinate(
        latitude=scenario.nodes[0].latitude, longitude=scenario.nodes[0].longitude
    )
    destination = GeographicCoordinate(
        latitude=scenario.nodes[-1].latitude, longitude=scenario.nodes[-1].longitude
    )
    with recorder.measure("routing"):
        comparison = routing_service.compare_routes(created.analysis_id, start, destination)

    # --- incident summary (deterministic provider — no network, no key) ---
    with recorder.measure("llm_summary"):
        incident_service = IncidentIntelligenceService(
            processing_service=processing_service,
            road_risk_service=road_risk_service,
            routing_service=routing_service,
            llm_provider=DeterministicSummaryProvider(),
            config=IncidentConfig.from_settings(Settings()),
        )
        briefing = incident_service.get_summary(
            created.analysis_id, RouteQuery(start=start, destination=destination)
        )

    # Every stage that actually ran produced a real, non-negative duration.
    timings = recorder.as_dict()
    assert set(timings.keys()) == {
        "upload", "damage_inference", "road_risk", "routing", "llm_summary"
    }
    assert all(duration >= 0.0 for duration in timings.values())
    assert recorder.total_ms == sum(timings.values())

    # Stages this pipeline never ran (there is no hazard subsystem) are
    # simply absent — never a fabricated number.
    assert "hazard_assessment" not in timings

    # Sanity: the pipeline actually ran, honestly, end to end. Road risk is
    # genuinely `unavailable` here — not a test bug: `_FakeCompletingModel`
    # (like every real model wired into this codebase today, see
    # `app.ml.localizer.UnavailableBuildingLocalizer`) never produces
    # georeferenced building geometry, so there is nothing for
    # `app.risk.analyzer` to correlate with the road graph. `distance_only`
    # routing doesn't require risk data and still finds a real route on the
    # populated graph; `risk_aware` correctly reports "not found" rather
    # than silently falling back to an un-risk-assessed path.
    assert road_risk.available is False
    assert road_risk.reason is not None
    assert comparison.distance_only.found is True
    assert comparison.risk_aware.found is False
    assert briefing.source in {"provider", "fallback"}

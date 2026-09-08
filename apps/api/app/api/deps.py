"""Shared FastAPI dependencies for the API layer.

Centralizing dependency providers here (rather than defining them inline
per-router) means a route only needs to declare the `*Dep` type alias it
wants, and swapping an implementation (e.g. for tests, via
`app.dependency_overrides`) never requires touching route code.
"""

import logging
import threading
from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.db.session import get_session_factory
from app.incident.anthropic_provider import AnthropicLLMProvider
from app.incident.config import IncidentConfig
from app.incident.fallback import DeterministicSummaryProvider
from app.incident.mock_provider import MockLLMProvider
from app.incident.provider import LLMProvider
from app.intelligence.config import CapabilityMatchingConfig, SearchPriorityConfig
from app.intelligence.demo_scenario import build_demo_scenario
from app.ml.classifier import TorchDamageClassifier
from app.ml.clip_classifier import ClipZeroShotDamageClassifier
from app.ml.inference import DamageInferenceEngine
from app.ml.localizer import BuildingLocalizer, UnavailableBuildingLocalizer
from app.ml.model import DamageModel, ModelLoadError, RawDetection, UnavailableDamageModel
from app.ml.pipeline import BuildingCropClassifier, TwoStageDamageModel
from app.ml.schemas import ModelStatus
from app.ml.tile_localizer import TileRegionLocalizer
from app.risk.config import RoadRiskConfig
from app.roads.osm_source import OverpassRoadNetworkSource, RoadNetworkSource
from app.routing.config import RoutingConfig
from app.services.analysis_intelligence_service import AnalysisIntelligenceService
from app.services.analysis_processing_service import AnalysisProcessingService
from app.services.analysis_repository import AnalysisRepository
from app.services.analysis_service import AnalysisService
from app.services.damage_map_service import DamageMapService
from app.services.file_storage import FileStorage, LocalFileStorage
from app.services.incident_intelligence_service import IncidentIntelligenceService
from app.services.intelligence_repository import (
    InMemoryIntelligenceRepository,
    IntelligenceRepository,
)
from app.services.intelligence_service import IntelligenceService
from app.services.job_queue import JobQueue, RedisJobQueue
from app.services.model_status_service import ModelStatusService
from app.services.postgres_analysis_repository import PostgresAnalysisRepository
from app.services.postgres_spatial_repository import PostgresSpatialRepository
from app.services.readiness_service import ReadinessService
from app.services.road_network_ingestion_service import RoadNetworkIngestionService
from app.services.road_network_repository import (
    InMemoryRoadNetworkRepository,
    RoadNetworkRepository,
)
from app.services.road_network_status_service import RoadNetworkStatusService
from app.services.road_risk_service import RoadRiskService
from app.services.routing_service import RoutingService
from app.services.spatial_repository import SpatialRepository
from app.services.system_service import SystemService
from app.services.worker_status import ModelStatusReader

logger = logging.getLogger(__name__)

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_system_service(settings: SettingsDep) -> SystemService:
    """Sample DI scaffold: construct a service from injected Settings.

    Future services follow the same shape — a `get_*_service` provider
    function, depended on by routes via an `Annotated[..., Depends(...)]`
    alias below.
    """
    return SystemService(settings)


SystemServiceDep = Annotated[SystemService, Depends(get_system_service)]


# Milestone F5: PostgreSQL-backed by default — production persistence,
# not a per-process dict. `PostgresAnalysisRepository` is a thin,
# stateless adapter (a fresh instance per call is cheap — no I/O in its
# constructor); the expensive part (the connection pool) is cached inside
# `get_session_factory`, keyed by `DATABASE_URL`, exactly like the F4
# model caches below are keyed by model config. Tests override this
# unconditionally with `InMemoryAnalysisRepository` (see
# `tests/conftest.py`) — never with a real database.
def get_analysis_repository(settings: SettingsDep) -> AnalysisRepository:
    return PostgresAnalysisRepository(get_session_factory(settings))


def get_file_storage(settings: SettingsDep) -> FileStorage:
    return LocalFileStorage(base_dir=settings.UPLOAD_DIR)


# See `get_analysis_repository` above — same reasoning.
# `PostgresSpatialRepository` reads from the *same* `building_damages`
# table `PostgresAnalysisRepository.save_result()` writes to (see that
# module's docstring for why `save_buildings()` is a no-op there).
def get_spatial_repository(settings: SettingsDep) -> SpatialRepository:
    return PostgresSpatialRepository(get_session_factory(settings))


# F3 needs `SpatialRepository` as a named `*Dep` (every existing call
# site until now used the bare `Annotated[...]` inline) — added here so
# `get_analysis_intelligence_service` below can depend on it the same
# way every other service dependency in this file is declared.
SpatialRepositoryDep = Annotated[SpatialRepository, Depends(get_spatial_repository)]


def get_analysis_service(
    settings: SettingsDep,
    repository: Annotated[AnalysisRepository, Depends(get_analysis_repository)],
    file_storage: Annotated[FileStorage, Depends(get_file_storage)],
) -> AnalysisService:
    return AnalysisService(settings=settings, repository=repository, file_storage=file_storage)


AnalysisServiceDep = Annotated[AnalysisService, Depends(get_analysis_service)]


# ML (Milestone 3A architecture, Milestone 3C concrete adapters, Milestone
# F4 real inference). `get_building_localizer`/`get_damage_classifier` are
# each backed by a small, module-level, config-keyed cache — see
# `_localizer_cache`/`_classifier_cache` below — so a real model (Milestone
# F4's CLIP checkpoint) is downloaded/loaded at most once per distinct
# configuration, never once per request (see apps/api/README.md,
# "Milestone F4 — real inference", "Model lifecycle"). `Settings.MODEL_ENABLED
# =False` (or `MODEL_PROVIDER="legacy_resnet"` with no checkpoint) restores
# the original Milestone 3A/3C honest-unavailable behavior exactly.
_localizer_cache: dict[tuple[bool, str, int], BuildingLocalizer] = {}
_localizer_cache_lock = threading.Lock()
_classifier_cache: dict[tuple[bool, str, str, str, str, str | None], BuildingCropClassifier] = {}
_classifier_cache_lock = threading.Lock()


class _LoadFailedClassifier:
    """Stand-in returned when a real classifier's `load()` genuinely
    failed (e.g. no network on first run) — never lets that failure
    propagate out of a dependency-injection call during
    `POST /api/v1/analysis` (which would otherwise crash the *upload*
    request itself, before background processing even starts — see
    "Model lifecycle" in apps/api/README.md). `classify()` instead raises
    `ModelLoadError` only when actually invoked, during background
    processing, where `AnalysisProcessingService.process()` already
    handles it as an honest `MODEL_LOAD_FAILURE` — never crashes the API.
    """

    def __init__(self, error: Exception, settings: Settings) -> None:
        self._error = error
        self._settings = settings

    def load(self) -> None:
        return None

    def classify(self, crop: object) -> RawDetection:
        raise ModelLoadError(str(self._error))

    def health(self) -> ModelStatus:
        return ModelStatus(
            model_loaded=False,
            model_name=self._settings.MODEL_NAME,
            model_version=self._settings.MODEL_VERSION,
            device=self._settings.MODEL_DEVICE,
        )


def get_building_localizer(settings: SettingsDep) -> BuildingLocalizer:
    key = (settings.MODEL_ENABLED, settings.MODEL_PROVIDER, settings.MODEL_TILE_GRID)
    cached = _localizer_cache.get(key)
    if cached is not None:
        return cached
    with _localizer_cache_lock:
        cached = _localizer_cache.get(key)
        if cached is not None:
            return cached
        localizer: BuildingLocalizer
        if settings.MODEL_ENABLED and settings.MODEL_PROVIDER == "open_clip":
            localizer = TileRegionLocalizer(grid_size=settings.MODEL_TILE_GRID)
        else:
            localizer = UnavailableBuildingLocalizer()
        localizer.load()  # never fails — deterministic tiling has no load step
        _localizer_cache[key] = localizer
        return localizer


BuildingLocalizerDep = Annotated[BuildingLocalizer, Depends(get_building_localizer)]


def get_damage_classifier(settings: SettingsDep) -> BuildingCropClassifier:
    key = (
        settings.MODEL_ENABLED,
        settings.MODEL_PROVIDER,
        settings.MODEL_NAME,
        settings.MODEL_VERSION,
        settings.MODEL_DEVICE,
        str(settings.MODEL_PATH) if settings.MODEL_PATH is not None else None,
    )
    cached = _classifier_cache.get(key)
    if cached is not None:
        return cached
    with _classifier_cache_lock:
        cached = _classifier_cache.get(key)
        if cached is not None:
            return cached
        classifier: BuildingCropClassifier
        if settings.MODEL_ENABLED and settings.MODEL_PROVIDER == "open_clip":
            classifier = ClipZeroShotDamageClassifier(settings)
        else:
            classifier = TorchDamageClassifier(settings)
        try:
            classifier.load()
        except ModelLoadError as exc:
            logger.exception("Damage classifier failed to load: %s", exc)
            classifier = _LoadFailedClassifier(exc, settings)
        _classifier_cache[key] = classifier
        return classifier


DamageClassifierDep = Annotated[BuildingCropClassifier, Depends(get_damage_classifier)]


def get_damage_model(
    localizer: BuildingLocalizerDep, classifier: DamageClassifierDep
) -> DamageModel:
    return TwoStageDamageModel(localizer=localizer, classifier=classifier)


DamageModelDep = Annotated[DamageModel, Depends(get_damage_model)]


def get_damage_inference_engine(
    model: DamageModelDep, settings: SettingsDep
) -> DamageInferenceEngine:
    return DamageInferenceEngine(model=model, max_image_dimension=settings.MODEL_MAX_IMAGE_DIM)


DamageInferenceEngineDep = Annotated[
    DamageInferenceEngine, Depends(get_damage_inference_engine)
]


# Milestone F5: read-only model readiness/status — `GET
# /api/v1/model/status`. Reads the worker's last-published status over
# Redis (`app.services.worker_status`) — **never** resolves
# `DamageModelDep` here, which would otherwise make the API process
# itself construct/load a real CLIP checkpoint on first request (F4's
# documented cold-start problem, now fixed: only the worker,
# `app/worker/main.py`, ever calls `get_damage_model` for real).
def get_model_status_reader(settings: SettingsDep) -> ModelStatusReader:
    return ModelStatusReader(settings.REDIS_URL)


ModelStatusReaderDep = Annotated[ModelStatusReader, Depends(get_model_status_reader)]


def get_model_status_service(
    settings: SettingsDep, reader: ModelStatusReaderDep
) -> ModelStatusService:
    return ModelStatusService(settings=settings, reader=reader)


ModelStatusServiceDep = Annotated[ModelStatusService, Depends(get_model_status_service)]


# Milestone F5: the background job queue — `POST /api/v1/analysis`
# enqueues here instead of using FastAPI `BackgroundTasks`. Deliberately
# does **not** depend on `AnalysisProcessingServiceDep`/`DamageModelDep`:
# the API process only ever enqueues a job id string onto Redis; it never
# imports or constructs the real inference stack. See
# `app/services/job_queue.py` and `app/worker/`.
def get_job_queue(settings: SettingsDep) -> JobQueue:
    return RedisJobQueue(settings.REDIS_URL, max_retries=settings.JOB_MAX_RETRIES)


JobQueueDep = Annotated[JobQueue, Depends(get_job_queue)]


# Milestone F5: `GET /ready` — real PostgreSQL + Redis connectivity
# checks, model status informational only. See
# `app/services/readiness_service.py`.
def get_readiness_service(
    settings: SettingsDep, model_status_reader: ModelStatusReaderDep
) -> ReadinessService:
    return ReadinessService(settings, model_status_reader)


ReadinessServiceDep = Annotated[ReadinessService, Depends(get_readiness_service)]


# Milestone 4 (originally); Milestone F5 changes what this constructs the
# inference engine *from*. The API process now only ever calls
# `.get_analysis()` on the result (a pure repository read) — `.process()`
# runs exclusively in the worker (`app/worker/tasks.py`, which builds its
# own separate `AnalysisProcessingService` wired to the real, eagerly-
# loaded model via `get_building_localizer`/`get_damage_classifier`
# below, called directly as plain functions, not through this file's
# FastAPI DI). Giving *this* (API-side) instance a real
# `DamageInferenceEngineDep` would make the API process construct/load a
# real CLIP checkpoint the moment any route resolves this dependency —
# exactly the in-API-process cold start F5 fixes. `UnavailableDamageModel`
# costs nothing to construct and its `predict()` is never called here.
def get_analysis_processing_service(
    repository: Annotated[AnalysisRepository, Depends(get_analysis_repository)],
    file_storage: Annotated[FileStorage, Depends(get_file_storage)],
    spatial_repository: Annotated[SpatialRepository, Depends(get_spatial_repository)],
    settings: SettingsDep,
) -> AnalysisProcessingService:
    inference_engine = DamageInferenceEngine(
        model=UnavailableDamageModel(settings),
        max_image_dimension=settings.MODEL_MAX_IMAGE_DIM,
    )
    return AnalysisProcessingService(
        repository=repository,
        file_storage=file_storage,
        inference_engine=inference_engine,
        spatial_repository=spatial_repository,
    )


AnalysisProcessingServiceDep = Annotated[
    AnalysisProcessingService, Depends(get_analysis_processing_service)
]


# Milestone 5: reads the spatial view AnalysisProcessingService writes.
def get_damage_map_service(
    processing_service: AnalysisProcessingServiceDep,
    spatial_repository: Annotated[SpatialRepository, Depends(get_spatial_repository)],
) -> DamageMapService:
    return DamageMapService(
        processing_service=processing_service, spatial_repository=spatial_repository
    )


DamageMapServiceDep = Annotated[DamageMapService, Depends(get_damage_map_service)]


# Milestone 6A: the road-network graph. Module-level singleton for the same
# reason `_analysis_repository` is one — plus it must start (and, absent an
# explicit ingestion call, stay) empty: no application startup or route
# downloads OSM data automatically. See app/roads/__init__.py.
_road_network_repository = InMemoryRoadNetworkRepository()


def get_road_network_repository() -> RoadNetworkRepository:
    return _road_network_repository


RoadNetworkRepositoryDep = Annotated[
    RoadNetworkRepository, Depends(get_road_network_repository)
]


def get_road_network_status_service(
    repository: RoadNetworkRepositoryDep,
) -> RoadNetworkStatusService:
    return RoadNetworkStatusService(repository=repository)


RoadNetworkStatusServiceDep = Annotated[
    RoadNetworkStatusService, Depends(get_road_network_status_service)
]


# The real, network-calling OSM source (app/roads/osm_source.py). Not
# consumed by any route this milestone — wired here so the future "load
# road network for bounding box" command has a ready DI seam, same pattern
# as BuildingLocalizerDep before any route used it.
def get_road_network_source() -> RoadNetworkSource:
    return OverpassRoadNetworkSource()


RoadNetworkSourceDep = Annotated[RoadNetworkSource, Depends(get_road_network_source)]


def get_road_network_ingestion_service(
    source: RoadNetworkSourceDep,
    repository: RoadNetworkRepositoryDep,
) -> RoadNetworkIngestionService:
    return RoadNetworkIngestionService(source=source, repository=repository)


RoadNetworkIngestionServiceDep = Annotated[
    RoadNetworkIngestionService, Depends(get_road_network_ingestion_service)
]


# Milestone 6B: connects Milestone 5's spatial damage data to Milestone 6A's
# road graph. RoadRiskConfig is derived fresh from Settings per request
# (cheap — a handful of float lookups) rather than cached as a singleton,
# so a Settings override (e.g. in tests) is always honored immediately.
def get_road_risk_config(settings: SettingsDep) -> RoadRiskConfig:
    return RoadRiskConfig.from_settings(settings)


RoadRiskConfigDep = Annotated[RoadRiskConfig, Depends(get_road_risk_config)]


def get_road_risk_service(
    processing_service: AnalysisProcessingServiceDep,
    spatial_repository: Annotated[SpatialRepository, Depends(get_spatial_repository)],
    road_network_repository: RoadNetworkRepositoryDep,
    config: RoadRiskConfigDep,
) -> RoadRiskService:
    return RoadRiskService(
        processing_service=processing_service,
        spatial_repository=spatial_repository,
        road_network_repository=road_network_repository,
        config=config,
    )


RoadRiskServiceDep = Annotated[RoadRiskService, Depends(get_road_risk_service)]


# Milestone 6C: connects the road graph (Milestone 6A) and its risk
# assessment (Milestone 6B) into an actual routing engine. RoutingConfig
# is derived fresh from Settings per request, same reasoning as
# RoadRiskConfigDep above.
def get_routing_config(settings: SettingsDep) -> RoutingConfig:
    return RoutingConfig.from_settings(settings)


RoutingConfigDep = Annotated[RoutingConfig, Depends(get_routing_config)]


def get_routing_service(
    road_network_repository: RoadNetworkRepositoryDep,
    road_risk_service: RoadRiskServiceDep,
    routing_config: RoutingConfigDep,
    risk_config: RoadRiskConfigDep,
) -> RoutingService:
    return RoutingService(
        road_network_repository=road_network_repository,
        road_risk_service=road_risk_service,
        routing_config=routing_config,
        risk_config=risk_config,
    )


RoutingServiceDep = Annotated[RoutingService, Depends(get_routing_service)]


# Milestone 7: LLM provider abstraction. Branches on Settings.LLM_PROVIDER
# so no other layer (service, route, test) ever imports a concrete
# provider directly. "anthropic" without an LLM_API_KEY configured falls
# back to the deterministic provider (with a warning) rather than raising
# at request time — consistent with "no API key -> still produce a valid
# incident briefing" from the milestone spec.
def get_llm_provider(settings: SettingsDep) -> LLMProvider:
    if settings.LLM_PROVIDER == "anthropic":
        if settings.LLM_API_KEY is None:
            logger.warning(
                "LLM_PROVIDER=anthropic but LLM_API_KEY is not set; "
                "falling back to the deterministic provider."
            )
            return DeterministicSummaryProvider()
        return AnthropicLLMProvider(
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
        )
    if settings.LLM_PROVIDER == "mock":
        return MockLLMProvider()
    return DeterministicSummaryProvider()


LLMProviderDep = Annotated[LLMProvider, Depends(get_llm_provider)]


def get_incident_config(settings: SettingsDep) -> IncidentConfig:
    return IncidentConfig.from_settings(settings)


IncidentConfigDep = Annotated[IncidentConfig, Depends(get_incident_config)]


def get_incident_intelligence_service(
    processing_service: AnalysisProcessingServiceDep,
    road_risk_service: RoadRiskServiceDep,
    routing_service: RoutingServiceDep,
    llm_provider: LLMProviderDep,
    config: IncidentConfigDep,
) -> IncidentIntelligenceService:
    return IncidentIntelligenceService(
        processing_service=processing_service,
        road_risk_service=road_risk_service,
        routing_service=routing_service,
        llm_provider=llm_provider,
        config=config,
    )


IncidentIntelligenceServiceDep = Annotated[
    IncidentIntelligenceService, Depends(get_incident_intelligence_service)
]


# F2: Disaster Intelligence Core. Module-level singleton for the same
# reason `_analysis_repository`/`_road_network_repository` are (see
# above) — plus it is seeded, exactly once at process start, with the
# deterministic DEMO scenario (`app.intelligence.demo_scenario`). This is
# deliberately different from `_road_network_repository`'s "starts empty,
# stays empty" convention: F2 has no real-disaster ingestion endpoint
# yet (only read endpoints — see `app/api/v1/endpoints/intelligence.py`),
# so without this seed the new endpoints would be permanently
# unreachable. It is safe precisely because every entity the demo
# scenario produces carries `is_simulated=True` (see
# `app.intelligence.schemas`) — this is not a real disaster silently
# masquerading as one, the same honesty guarantee
# `apps/web/src/lib/demo/demo-data.ts`'s frontend fixtures already give.
_intelligence_repository = InMemoryIntelligenceRepository()
_intelligence_repository.save_scenario(build_demo_scenario())


def get_intelligence_repository() -> IntelligenceRepository:
    return _intelligence_repository


IntelligenceRepositoryDep = Annotated[
    IntelligenceRepository, Depends(get_intelligence_repository)
]


def get_search_priority_config(settings: SettingsDep) -> SearchPriorityConfig:
    return SearchPriorityConfig.from_settings(settings)


SearchPriorityConfigDep = Annotated[SearchPriorityConfig, Depends(get_search_priority_config)]


def get_capability_matching_config(settings: SettingsDep) -> CapabilityMatchingConfig:
    return CapabilityMatchingConfig.from_settings(settings)


CapabilityMatchingConfigDep = Annotated[
    CapabilityMatchingConfig, Depends(get_capability_matching_config)
]


def get_intelligence_service(
    repository: IntelligenceRepositoryDep,
    search_priority_config: SearchPriorityConfigDep,
    capability_matching_config: CapabilityMatchingConfigDep,
) -> IntelligenceService:
    return IntelligenceService(
        repository=repository,
        search_priority_config=search_priority_config,
        capability_matching_config=capability_matching_config,
    )


IntelligenceServiceDep = Annotated[IntelligenceService, Depends(get_intelligence_service)]


# F3: adapts real analysis data into F2's DisasterScenario/IntelligenceService
# pipeline (see app/intelligence/analysis_adapter.py and
# app/services/analysis_intelligence_service.py) — depends on the same
# analysis/spatial/road-risk/routing services the existing
# `/api/v1/analysis/{analysis_id}/...` endpoints already use, plus
# IntelligenceServiceDep (F2) for the actual scoring/recommendation
# logic, reused unmodified.
def get_analysis_intelligence_service(
    processing_service: AnalysisProcessingServiceDep,
    spatial_repository: SpatialRepositoryDep,
    road_risk_service: RoadRiskServiceDep,
    routing_service: RoutingServiceDep,
    intelligence_service: IntelligenceServiceDep,
    capability_matching_config: CapabilityMatchingConfigDep,
) -> AnalysisIntelligenceService:
    return AnalysisIntelligenceService(
        processing_service=processing_service,
        spatial_repository=spatial_repository,
        road_risk_service=road_risk_service,
        routing_service=routing_service,
        intelligence_service=intelligence_service,
        capability_matching_config=capability_matching_config,
    )


AnalysisIntelligenceServiceDep = Annotated[
    AnalysisIntelligenceService, Depends(get_analysis_intelligence_service)
]

"""Shared FastAPI dependencies for the API layer.

Centralizing dependency providers here (rather than defining them inline
per-router) means a route only needs to declare the `*Dep` type alias it
wants, and swapping an implementation (e.g. for tests, via
`app.dependency_overrides`) never requires touching route code.
"""

import logging
from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.incident.anthropic_provider import AnthropicLLMProvider
from app.incident.config import IncidentConfig
from app.incident.fallback import DeterministicSummaryProvider
from app.incident.mock_provider import MockLLMProvider
from app.incident.provider import LLMProvider
from app.ml.classifier import TorchDamageClassifier
from app.ml.inference import DamageInferenceEngine
from app.ml.localizer import BuildingLocalizer, UnavailableBuildingLocalizer
from app.ml.model import DamageModel
from app.ml.pipeline import TwoStageDamageModel
from app.risk.config import RoadRiskConfig
from app.roads.osm_source import OverpassRoadNetworkSource, RoadNetworkSource
from app.routing.config import RoutingConfig
from app.services.analysis_processing_service import AnalysisProcessingService
from app.services.analysis_repository import AnalysisRepository, InMemoryAnalysisRepository
from app.services.analysis_service import AnalysisService
from app.services.damage_map_service import DamageMapService
from app.services.file_storage import FileStorage, LocalFileStorage
from app.services.incident_intelligence_service import IncidentIntelligenceService
from app.services.road_network_ingestion_service import RoadNetworkIngestionService
from app.services.road_network_repository import (
    InMemoryRoadNetworkRepository,
    RoadNetworkRepository,
)
from app.services.road_network_status_service import RoadNetworkStatusService
from app.services.road_risk_service import RoadRiskService
from app.services.routing_service import RoutingService
from app.services.spatial_repository import InMemorySpatialRepository, SpatialRepository
from app.services.system_service import SystemService

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


# Module-level singleton: an in-memory repository must be the *same*
# instance across requests to remember anything between calls at all — a
# fresh instance per request would make every analysis vanish immediately
# after being created. Replaced by a database-backed repository (and a
# request-scoped session dependency) once persistence is introduced.
_analysis_repository = InMemoryAnalysisRepository()


def get_analysis_repository() -> AnalysisRepository:
    return _analysis_repository


def get_file_storage(settings: SettingsDep) -> FileStorage:
    return LocalFileStorage(base_dir=settings.UPLOAD_DIR)


# Module-level singleton for the same reason `_analysis_repository` is one
# (see above) — plus it must be the *same* instance `AnalysisProcessingService`
# writes to and `DamageMapService` reads from (see
# `app/services/spatial_repository.py`).
_spatial_repository = InMemorySpatialRepository()


def get_spatial_repository() -> SpatialRepository:
    return _spatial_repository


def get_analysis_service(
    settings: SettingsDep,
    repository: Annotated[AnalysisRepository, Depends(get_analysis_repository)],
    file_storage: Annotated[FileStorage, Depends(get_file_storage)],
) -> AnalysisService:
    return AnalysisService(settings=settings, repository=repository, file_storage=file_storage)


AnalysisServiceDep = Annotated[AnalysisService, Depends(get_analysis_service)]


# ML (Milestone 3A architecture, Milestone 3C concrete adapters). Not yet
# consumed by any route — this wiring is what a future inference endpoint
# will depend on directly, without any further DI plumbing. Both stages
# report "unavailable" honestly until a real building-localization model
# and a fine-tuned classifier checkpoint exist — see apps/api/README.md.
def get_building_localizer() -> BuildingLocalizer:
    return UnavailableBuildingLocalizer()


BuildingLocalizerDep = Annotated[BuildingLocalizer, Depends(get_building_localizer)]


def get_damage_classifier(settings: SettingsDep) -> TorchDamageClassifier:
    classifier = TorchDamageClassifier(settings)
    classifier.load()
    return classifier


DamageClassifierDep = Annotated[TorchDamageClassifier, Depends(get_damage_classifier)]


def get_damage_model(
    localizer: BuildingLocalizerDep, classifier: DamageClassifierDep
) -> DamageModel:
    return TwoStageDamageModel(localizer=localizer, classifier=classifier)


DamageModelDep = Annotated[DamageModel, Depends(get_damage_model)]


def get_damage_inference_engine(model: DamageModelDep) -> DamageInferenceEngine:
    return DamageInferenceEngine(model=model)


DamageInferenceEngineDep = Annotated[
    DamageInferenceEngine, Depends(get_damage_inference_engine)
]


# Milestone 4: connects the upload lifecycle (AnalysisRepository/FileStorage
# above) to the ML inference architecture (DamageInferenceEngineDep above).
def get_analysis_processing_service(
    repository: Annotated[AnalysisRepository, Depends(get_analysis_repository)],
    file_storage: Annotated[FileStorage, Depends(get_file_storage)],
    inference_engine: DamageInferenceEngineDep,
    spatial_repository: Annotated[SpatialRepository, Depends(get_spatial_repository)],
) -> AnalysisProcessingService:
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

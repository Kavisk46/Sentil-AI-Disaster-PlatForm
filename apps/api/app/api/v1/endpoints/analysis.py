"""Analysis lifecycle endpoints.

`POST /api/v1/analysis` accepts an aerial/satellite image, creates an
analysis record, and dispatches it for processing. `GET
/api/v1/analysis/{analysis_id}` returns its current lifecycle state and,
once available, its result. `GET
/api/v1/analysis/{analysis_id}/damage-map` (Milestone 5) returns the
spatial (GeoJSON) representation of that same result. `GET
/api/v1/analysis/{analysis_id}/road-risk` (Milestone 6B) returns the
risk-aware road representation correlating that same result with the
OpenStreetMap road graph (Milestone 6A). `GET`/`POST
/api/v1/analysis/{analysis_id}/summary` (Milestone 7) return an
AI-assisted, structured incident briefing synthesized from that same
damage/road-risk/(optional) routing data.

Routes translate HTTP <-> schema and delegate; validation, storage, and
lifecycle orchestration all live in `AnalysisService`/
`AnalysisProcessingService`/`DamageMapService`/`RoadRiskService`/
`IncidentIntelligenceService`, and error handling in
`app/api/exception_handlers.py` — no model-inference, geometry, or LLM
logic lives here (see `app/services/analysis_processing_service.py`,
`app/services/damage_map_service.py`, `app/services/road_risk_service.py`,
and `app/services/incident_intelligence_service.py` for the actual
pipelines).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, UploadFile, status

from app.api.deps import (
    AnalysisProcessingServiceDep,
    AnalysisServiceDep,
    DamageMapServiceDep,
    IncidentIntelligenceServiceDep,
    RoadRiskServiceDep,
)
from app.incident.schemas import IncidentBriefing
from app.ml.schemas import DamageAnalysis
from app.schemas.analysis import AnalysisCreateResponse
from app.schemas.damage_map import DamageMapResponse
from app.schemas.incident import IncidentSummaryRequest
from app.schemas.road_risk import RoadRiskResponse

router = APIRouter(prefix="/analysis", tags=["analysis"])

# Annotated (rather than `image: UploadFile = File(...)`) matches this
# codebase's DI convention elsewhere (see `*Dep` aliases in app/api/deps.py)
# and avoids relying on a mutable default-argument value.
ImageUpload = Annotated[
    UploadFile, File(description="Aerial/satellite image (JPEG, PNG, or WEBP).")
]


@router.post(
    "",
    response_model=AnalysisCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an image for analysis",
)
def create_analysis(
    analysis_service: AnalysisServiceDep,
    processing_service: AnalysisProcessingServiceDep,
    background_tasks: BackgroundTasks,
    image: ImageUpload,
) -> AnalysisCreateResponse:
    upload = analysis_service.create_analysis(image)

    # Fast, synchronous hand-off to `queued`, then the actual pipeline
    # (queued -> processing -> completed/failed) runs after this response
    # has been sent — see app/services/analysis_processing_service.py for
    # why this doesn't need Redis/Celery/Kafka.
    queued = processing_service.enqueue(upload.analysis_id)
    background_tasks.add_task(processing_service.process, upload.analysis_id)

    return AnalysisCreateResponse(
        analysis_id=upload.analysis_id, status=queued.status, filename=upload.filename
    )


@router.get(
    "/{analysis_id}",
    response_model=DamageAnalysis,
    status_code=status.HTTP_200_OK,
    summary="Get analysis status/result",
)
def get_analysis(
    analysis_id: UUID,
    processing_service: AnalysisProcessingServiceDep,
) -> DamageAnalysis:
    return processing_service.get_analysis(analysis_id)


@router.get(
    "/{analysis_id}/damage-map",
    response_model=DamageMapResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the spatial damage map (GeoJSON) for an analysis",
)
def get_damage_map(
    analysis_id: UUID,
    damage_map_service: DamageMapServiceDep,
) -> DamageMapResponse:
    return damage_map_service.get_damage_map(analysis_id)


@router.get(
    "/{analysis_id}/road-risk",
    response_model=RoadRiskResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the risk-aware road representation for an analysis",
)
def get_road_risk(
    analysis_id: UUID,
    road_risk_service: RoadRiskServiceDep,
) -> RoadRiskResponse:
    return road_risk_service.get_road_risk(analysis_id)


@router.get(
    "/{analysis_id}/summary",
    response_model=IncidentBriefing,
    status_code=status.HTTP_200_OK,
    summary="Get an AI-assisted incident briefing for an analysis",
)
def get_incident_summary(
    analysis_id: UUID,
    incident_service: IncidentIntelligenceServiceDep,
) -> IncidentBriefing:
    return incident_service.get_summary(analysis_id)


@router.post(
    "/{analysis_id}/summary",
    response_model=IncidentBriefing,
    status_code=status.HTTP_200_OK,
    summary="Regenerate an incident briefing, optionally enriched with routing context",
)
def regenerate_incident_summary(
    analysis_id: UUID,
    incident_service: IncidentIntelligenceServiceDep,
    request: IncidentSummaryRequest | None = None,
) -> IncidentBriefing:
    route_query = request.route if request is not None else None
    return incident_service.get_summary(analysis_id, route_query)

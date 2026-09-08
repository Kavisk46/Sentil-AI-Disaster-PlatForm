"""Analysis lifecycle endpoints.

`POST /api/v1/analysis` accepts an aerial/satellite image, creates an
analysis record, and dispatches it for processing. Milestone F5: the
analysis record and its buildings are now persisted in PostgreSQL (not an
in-process dict), and processing is dispatched onto a Redis-backed job
queue (`app/services/job_queue.py`) for a separate worker process
(`app/worker/`) to actually run — the API process itself never
constructs or loads the real inference model, and this response's shape
and status code (`201`) are unchanged from Milestone 4. `GET
/api/v1/analysis/{analysis_id}` returns its current lifecycle state and,
once available, its result. `GET
/api/v1/analysis/{analysis_id}/damage-map` (Milestone 5) returns the
spatial (GeoJSON) representation of that same result. `GET
/api/v1/analysis/{analysis_id}/road-risk` (Milestone 6B) returns the
risk-aware road representation correlating that same result with the
OpenStreetMap road graph (Milestone 6A). `GET`/`POST
/api/v1/analysis/{analysis_id}/summary` (Milestone 7) return an
AI-assisted, structured incident briefing synthesized from that same
damage/road-risk/(optional) routing data. `GET
/api/v1/analysis/{analysis_id}/intelligence[/search-zones|/recommendations]`
(**Milestone F3**) adapt that same real analysis data into F2's
Disaster Intelligence Core domain model and run its deterministic
search-priority/capability-matching/recommendation pipeline against it —
see `app/intelligence/analysis_adapter.py` and
`app/services/analysis_intelligence_service.py`. Distinct from
`/api/v1/intelligence/{disaster_id}...` (F2, unchanged): that path
serves the deterministic demo scenario by a `disaster_id`; this path
serves real analysis-derived data by the existing `analysis_id`.

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

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from redis.exceptions import RedisError

from app.api.deps import (
    AnalysisIntelligenceServiceDep,
    AnalysisProcessingServiceDep,
    AnalysisServiceDep,
    DamageMapServiceDep,
    IncidentIntelligenceServiceDep,
    JobQueueDep,
    RoadRiskServiceDep,
)
from app.incident.schemas import IncidentBriefing
from app.ml.schemas import DamageAnalysis
from app.schemas.analysis import AnalysisCreateResponse
from app.schemas.analysis_intelligence import (
    AnalysisIntelligenceContextResponse,
    AnalysisRecommendationsResponse,
    AnalysisSearchZonesResponse,
)
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
    job_queue: JobQueueDep,
    image: ImageUpload,
) -> AnalysisCreateResponse:
    upload = analysis_service.create_analysis(image)

    # Fast hand-off to `queued`, committed to the database, *then*
    # enqueued onto Redis — never the other way around (see
    # `docs/architecture/production.md`, "Database transactions": a job
    # must never reference an analysis id the database doesn't durably
    # know about yet). The actual pipeline (queued -> processing ->
    # completed/failed) now runs in a separate worker process
    # (`app/worker/`), not FastAPI `BackgroundTasks` — the API process
    # returns immediately regardless of how long inference takes.
    queued = processing_service.enqueue(upload.analysis_id)
    try:
        job_queue.enqueue_analysis(upload.analysis_id)
    except RedisError as exc:
        # The analysis record is already durably persisted (status
        # `queued`) — never lost, even though it was never actually
        # enqueued. A clean, honest 503 rather than a bare, unhandled
        # 500: the client can retry (a fresh upload, or — once a manual
        # requeue operation exists — the same analysis_id), and the
        # record itself remains inspectable via `GET .../{analysis_id}`.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The analysis was recorded but could not be queued for processing "
                "(job queue unavailable). It remains retrievable; please try again."
            ),
        ) from exc

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


@router.get(
    "/{analysis_id}/intelligence",
    response_model=AnalysisIntelligenceContextResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the Disaster Intelligence Core context derived from an analysis (Milestone F3)",
)
def get_analysis_intelligence_context(
    analysis_id: UUID,
    service: AnalysisIntelligenceServiceDep,
) -> AnalysisIntelligenceContextResponse:
    return service.get_context_summary(analysis_id)


@router.get(
    "/{analysis_id}/intelligence/search-zones",
    response_model=AnalysisSearchZonesResponse,
    status_code=status.HTTP_200_OK,
    summary="Get search zones scored from an analysis's real damage data (Milestone F3)",
)
def get_analysis_search_zones(
    analysis_id: UUID,
    service: AnalysisIntelligenceServiceDep,
) -> AnalysisSearchZonesResponse:
    return service.get_search_zones(analysis_id)


@router.get(
    "/{analysis_id}/intelligence/recommendations",
    response_model=AnalysisRecommendationsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get rule-based recommendations derived from an analysis (Milestone F3)",
)
def get_analysis_recommendations(
    analysis_id: UUID,
    service: AnalysisIntelligenceServiceDep,
) -> AnalysisRecommendationsResponse:
    return service.get_recommendations(analysis_id)

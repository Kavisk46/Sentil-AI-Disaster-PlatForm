"""Disaster Intelligence Core read endpoints (F2).

Path parameter is `disaster_id`, not `incident_id`: this domain's
`Disaster` (`app.intelligence.schemas`) is a broader concept than an
`analysis_id`-scoped image analysis — it spans observations, hazards,
resources, and infrastructure, not one uploaded image — so it gets its
own identifier rather than overloading `analysis_id`'s existing meaning.

Every route here does nothing but call `IntelligenceServiceDep` and
return its result — no business logic in routes, same convention as
every other endpoints module (see `app/api/v1/endpoints/roads.py`).
`DisasterNotFoundError` propagates to `app/api/exception_handlers.py`,
which maps it to `404`.
"""

from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import IntelligenceServiceDep
from app.schemas.intelligence import (
    DisasterSummaryResponse,
    RecommendationListResponse,
    ResourceListResponse,
    SearchZoneListResponse,
)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get(
    "/{disaster_id}",
    response_model=DisasterSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Disaster record and a count of every recorded intelligence entity",
)
def get_disaster_summary(
    disaster_id: UUID, service: IntelligenceServiceDep
) -> DisasterSummaryResponse:
    scenario = service.get_disaster_scenario(disaster_id)
    return DisasterSummaryResponse(
        disaster=scenario.disaster,
        observation_count=len(scenario.observations),
        affected_area_count=len(scenario.affected_areas),
        hazard_count=len(scenario.hazards),
        resource_count=len(scenario.resources),
        infrastructure_count=len(scenario.infrastructure),
        route_count=len(scenario.routes),
    )


@router.get(
    "/{disaster_id}/search-zones",
    response_model=SearchZoneListResponse,
    status_code=status.HTTP_200_OK,
    summary="Ranked search zones, scored from recorded affected areas",
)
def get_search_zones(disaster_id: UUID, service: IntelligenceServiceDep) -> SearchZoneListResponse:
    return SearchZoneListResponse(
        disaster_id=disaster_id, search_zones=service.get_search_zones(disaster_id)
    )


@router.get(
    "/{disaster_id}/resources",
    response_model=ResourceListResponse,
    status_code=status.HTTP_200_OK,
    summary="The recorded resource registry for this disaster",
)
def get_resources(disaster_id: UUID, service: IntelligenceServiceDep) -> ResourceListResponse:
    return ResourceListResponse(
        disaster_id=disaster_id, resources=service.get_resources(disaster_id)
    )


@router.get(
    "/{disaster_id}/recommendations",
    response_model=RecommendationListResponse,
    status_code=status.HTTP_200_OK,
    summary="Ranked, rule-based response recommendations",
)
def get_recommendations(
    disaster_id: UUID, service: IntelligenceServiceDep
) -> RecommendationListResponse:
    return RecommendationListResponse(
        disaster_id=disaster_id, recommendations=service.get_recommendations(disaster_id)
    )

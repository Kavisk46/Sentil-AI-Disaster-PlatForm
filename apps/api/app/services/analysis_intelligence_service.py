"""**F3**: the analysis-aware intelligence pipeline —

    AnalysisProcessingService.get_analysis() -> DamageAnalysis
    SpatialRepository.get_buildings()        -> list[BuildingDamage]
    RoadRiskService.get_road_risk()          -> RoadRiskResponse
        -> app.intelligence.analysis_adapter.build_context_from_analysis()
        -> DisasterScenario
        -> IntelligenceService.score_zones_for_scenario/recommendations_for_scenario  [F2, reused]
        -> optionally enriched with a real RoutingService.route() call for the
           top search zone's best resource candidate — "route feasibility"

Kept as its own service, same reasoning as every other `*Service` split
in this codebase: this is DI-facing orchestration (fetch, adapt, score,
optionally enrich with routing); the actual scoring/matching/
recommendation math lives entirely in `app.intelligence`, unchanged by
F3, testable independently of this class or the HTTP layer.

**Nothing here is cached.** Every method recomputes from the analysis
pipeline's current state on every call — the same "always fresh, never
stale" principle `IntelligenceService` already established for F2's own
disaster-scoped scores.
"""

from uuid import UUID

from app.intelligence.analysis_adapter import (
    AnalysisContextResult,
    build_context_from_analysis,
    derive_disaster_id,
)
from app.intelligence.capability_matching import rank_candidates, resource_id_map
from app.intelligence.config import CapabilityMatchingConfig
from app.intelligence.schemas import CapabilityMatchResult, Resource, ResourceCapability, SearchZone
from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.risk.spatial import representative_point
from app.roads.schemas import GeographicCoordinate
from app.routing.schemas import RouteResult, RoutingMode
from app.schemas.analysis_intelligence import (
    AnalysisCapabilityMatch,
    AnalysisIntelligenceContextResponse,
    AnalysisRecommendationsResponse,
    AnalysisSearchZonesResponse,
    RouteFeasibilityStatus,
)
from app.schemas.road_risk import RoadRiskResponse
from app.schemas.routing import RoutingRequest
from app.services.analysis_processing_service import AnalysisProcessingService
from app.services.intelligence_repository import DisasterScenario
from app.services.intelligence_service import IntelligenceService
from app.services.road_risk_service import RoadRiskService
from app.services.routing_service import RoutingService
from app.services.spatial_repository import SpatialRepository

# The recommendation rules this service reuses from app.intelligence.recommendation
# only ever ask for GROUND_SEARCH when matching a search zone (see
# _recommendation_for_search_zone) — mirrored here for the route-feasibility
# enrichment step so it checks the same candidate pool the recommendation
# itself was based on, not a different one.
_DEPLOYMENT_CAPABILITY = [ResourceCapability.GROUND_SEARCH]


class AnalysisIntelligenceService:
    def __init__(
        self,
        processing_service: AnalysisProcessingService,
        spatial_repository: SpatialRepository,
        road_risk_service: RoadRiskService,
        routing_service: RoutingService,
        intelligence_service: IntelligenceService,
        capability_matching_config: CapabilityMatchingConfig,
    ) -> None:
        self._processing_service = processing_service
        self._spatial_repository = spatial_repository
        self._road_risk_service = road_risk_service
        self._routing_service = routing_service
        self._intelligence_service = intelligence_service
        self._capability_matching_config = capability_matching_config

    def _build_context(self, analysis_id: UUID) -> tuple[AnalysisContextResult, RoadRiskResponse]:
        """Raises `AnalysisNotFoundError` (-> `404`) if `analysis_id` is
        unknown — the same contract every other analysis-scoped service
        already has."""
        analysis = self._processing_service.get_analysis(analysis_id)
        buildings = self._spatial_repository.get_buildings(analysis_id) or []
        road_risk = self._road_risk_service.get_road_risk(analysis_id)
        context = build_context_from_analysis(analysis, buildings, road_risk)
        return context, road_risk

    def get_context_summary(self, analysis_id: UUID) -> AnalysisIntelligenceContextResponse:
        context, road_risk = self._build_context(analysis_id)
        disaster_id = derive_disaster_id(analysis_id)

        if not context.available:
            assert context.unavailable_reason is not None
            return AnalysisIntelligenceContextResponse(
                analysis_id=analysis_id,
                disaster_id=disaster_id,
                context_available=False,
                context_unavailable_reason=context.unavailable_reason.value,
                is_simulated=False,
                roads_available=road_risk.available,
                roads_unavailable_reason=road_risk.reason,
                resources_available=True,
                resources_are_demo=True,
            )

        scenario = context.scenario
        assert scenario is not None
        return AnalysisIntelligenceContextResponse(
            analysis_id=analysis_id,
            disaster_id=disaster_id,
            context_available=True,
            context_unavailable_reason=None,
            is_simulated=False,
            affected_area_count=len(scenario.affected_areas),
            hazard_count=len(scenario.hazards),
            infrastructure_count=len(scenario.infrastructure),
            roads_available=road_risk.available,
            roads_unavailable_reason=road_risk.reason,
            resources_available=True,
            resources_are_demo=True,
        )

    def get_search_zones(self, analysis_id: UUID) -> AnalysisSearchZonesResponse:
        context, _road_risk = self._build_context(analysis_id)
        disaster_id = derive_disaster_id(analysis_id)

        if not context.available:
            assert context.unavailable_reason is not None
            return AnalysisSearchZonesResponse(
                analysis_id=analysis_id,
                disaster_id=disaster_id,
                context_available=False,
                context_unavailable_reason=context.unavailable_reason.value,
            )

        assert context.scenario is not None
        zones = self._intelligence_service.score_zones_for_scenario(context.scenario)
        return AnalysisSearchZonesResponse(
            analysis_id=analysis_id,
            disaster_id=disaster_id,
            context_available=True,
            context_unavailable_reason=None,
            search_zones=zones,
        )

    def get_recommendations(self, analysis_id: UUID) -> AnalysisRecommendationsResponse:
        context, road_risk = self._build_context(analysis_id)
        disaster_id = derive_disaster_id(analysis_id)

        if not context.available:
            assert context.unavailable_reason is not None
            return AnalysisRecommendationsResponse(
                analysis_id=analysis_id,
                disaster_id=disaster_id,
                context_available=False,
                context_unavailable_reason=context.unavailable_reason.value,
                resources_are_demo=True,
                roads_available=road_risk.available,
                roads_unavailable_reason=road_risk.reason,
            )

        scenario = context.scenario
        assert scenario is not None
        zones = self._intelligence_service.score_zones_for_scenario(scenario)
        recommendations = self._intelligence_service.recommendations_for_scenario(scenario, zones)

        top_zone_id = zones[0].id if zones else None
        candidates: list[AnalysisCapabilityMatch] = []
        if zones:
            candidates = self._match_candidates_for_zone(
                analysis_id, zones[0], scenario, roads_available=road_risk.available
            )

        return AnalysisRecommendationsResponse(
            analysis_id=analysis_id,
            disaster_id=disaster_id,
            context_available=True,
            context_unavailable_reason=None,
            recommendations=recommendations,
            top_search_zone_id=top_zone_id,
            resource_candidates=candidates,
            resources_are_demo=True,
            roads_available=road_risk.available,
            roads_unavailable_reason=road_risk.reason,
        )

    def _match_candidates_for_zone(
        self,
        analysis_id: UUID,
        zone: SearchZone,
        scenario: DisasterScenario,
        *,
        roads_available: bool,
    ) -> list[AnalysisCapabilityMatch]:
        """Ranks every resource against `zone` (reusing
        `app.intelligence.capability_matching` unmodified), then
        attempts a real, computed route
        (`app.services.routing_service.RoutingService`, the same engine
        `POST /api/v1/routing` uses) for the single top-ranked candidate
        — never for every candidate, to keep this bounded, and never
        fabricating route geometry when it can't be computed.
        """
        matches = rank_candidates(
            required_capabilities=_DEPLOYMENT_CAPABILITY,
            target_geometry=zone.geometry,
            target_geometry_crs=zone.geometry_crs,
            resources=list(scenario.resources),
            config=self._capability_matching_config,
        )
        resources_by_id = resource_id_map(list(scenario.resources))

        results: list[AnalysisCapabilityMatch] = []
        for index, match in enumerate(matches):
            route: RouteResult | None = None
            if not match.eligible:
                feasibility = RouteFeasibilityStatus(
                    status="not_applicable",
                    reason=(
                        "Candidate did not pass an earlier capability/availability/"
                        "reachability gate."
                    ),
                )
            elif index == 0:
                route, feasibility = self._attempt_route(
                    analysis_id, match, resources_by_id, zone, roads_available=roads_available
                )
            else:
                feasibility = RouteFeasibilityStatus(
                    status="not_applicable",
                    reason=(
                        "Route feasibility is only computed for the single top-ranked candidate."
                    ),
                )
            results.append(
                AnalysisCapabilityMatch(match=match, route=route, route_feasibility=feasibility)
            )
        return results

    def _attempt_route(
        self,
        analysis_id: UUID,
        match: CapabilityMatchResult,
        resources_by_id: dict[UUID, Resource],
        zone: SearchZone,
        *,
        roads_available: bool,
    ) -> tuple[RouteResult | None, RouteFeasibilityStatus]:
        resource = resources_by_id.get(match.resource_id)
        if not roads_available:
            return None, RouteFeasibilityStatus(
                status="route_unavailable", reason="No road network is loaded for this analysis."
            )
        if resource is None or resource.location is None:
            return None, RouteFeasibilityStatus(
                status="route_unavailable", reason="Candidate resource has no known location."
            )
        if (
            resource.location_crs is not CoordinateReferenceSystem.WGS84
            or zone.geometry_crs is not CoordinateReferenceSystem.WGS84
        ):
            return None, RouteFeasibilityStatus(
                status="route_unavailable",
                reason=(
                    "Resource or search-zone geometry is not a tagged geographic (WGS84) "
                    "coordinate — never treated as one."
                ),
            )

        start_lon, start_lat = representative_point(resource.location)
        destination_lon, destination_lat = representative_point(zone.geometry)
        # Reuses the exact routing engine `POST /api/v1/routing` calls —
        # no second pathfinder, no invented geometry. Uses the real
        # analysis_id so RoutingService's own internal RoadRiskService
        # lookup resolves to this analysis's actual risk data.
        route_result = self._routing_service.route(
            RoutingRequest(
                analysis_id=analysis_id,
                start=GeographicCoordinate(latitude=start_lat, longitude=start_lon),
                destination=GeographicCoordinate(
                    latitude=destination_lat, longitude=destination_lon
                ),
                mode=RoutingMode.RISK_AWARE,
            )
        )
        return route_result, RouteFeasibilityStatus(status="computed", reason=None)

"""Assembles an `IncidentBriefing`:

    API -> IncidentIntelligenceService (this file) -> Context Builder
        -> LLM Provider -> Schema Validation -> Incident Briefing

Fetches analysis/road-risk/(optional) routing context via the *existing*
services (`AnalysisProcessingService`, `RoadRiskService`, `RoutingService`
— no new repository, no duplicated lookup logic), hands it to
`app.incident.context_builder`, then runs the configured `LLMProvider`
through a strict pipeline: generate -> parse -> ground -> assemble. Any
failure at any stage (`LLMProviderError`/`LLMTimeoutError`, malformed
JSON, an unsupported claim) falls back to the deterministic template
narrative (`app.incident.fallback`) — the client always receives a valid
`IncidentBriefing`, never a 500, never a partially-assembled result.
"""

import logging
from typing import Literal
from uuid import UUID

from app.incident.briefing_builder import assemble_briefing
from app.incident.config import IncidentConfig
from app.incident.context_builder import build_incident_context
from app.incident.fallback import build_fallback_narrative
from app.incident.grounding import filter_unsupported_claims
from app.incident.provider import LLMProvider, LLMProviderError
from app.incident.schemas import IncidentBriefing, IncidentContext, LLMNarrativeOutput
from app.incident.validator import parse_llm_output
from app.schemas.incident import RouteQuery
from app.services.analysis_processing_service import AnalysisProcessingService
from app.services.road_risk_service import RoadRiskService
from app.services.routing_service import RoutingService

logger = logging.getLogger(__name__)


class IncidentIntelligenceService:
    def __init__(
        self,
        processing_service: AnalysisProcessingService,
        road_risk_service: RoadRiskService,
        routing_service: RoutingService,
        llm_provider: LLMProvider,
        config: IncidentConfig,
    ) -> None:
        self._processing_service = processing_service
        self._road_risk_service = road_risk_service
        self._routing_service = routing_service
        self._llm_provider = llm_provider
        self._config = config

    def get_summary(
        self, analysis_id: UUID, route_query: RouteQuery | None = None
    ) -> IncidentBriefing:
        """Raises `AnalysisNotFoundError` (-> `404`) if `analysis_id` is
        unknown — the same contract as `RoadRiskService.get_road_risk`."""
        context = self._build_context(analysis_id, route_query)
        narrative, source = self._get_narrative(context)
        return assemble_briefing(context, narrative, source, self._config)

    def _build_context(self, analysis_id: UUID, route_query: RouteQuery | None) -> IncidentContext:
        # get_road_risk() also performs the analysis-existence check (it
        # calls AnalysisProcessingService.get_analysis internally), so a
        # single call covers both the damage and road-risk lookups'
        # not-found behavior.
        road_risk = self._road_risk_service.get_road_risk(analysis_id)
        analysis = self._processing_service.get_analysis(analysis_id)

        comparison = None
        if route_query is not None:
            comparison = self._routing_service.compare_routes(
                analysis_id, route_query.start, route_query.destination
            )

        return build_incident_context(analysis, road_risk, comparison, self._config)

    def _get_narrative(
        self, context: IncidentContext
    ) -> tuple[LLMNarrativeOutput, Literal["provider", "fallback"]]:
        try:
            raw = self._llm_provider.generate_incident_summary(context)
        except LLMProviderError:
            logger.warning(
                "LLM provider failed for analysis_id=%s; using deterministic fallback.",
                context.analysis_id,
                exc_info=True,
            )
            return build_fallback_narrative(context), "fallback"

        parsed = parse_llm_output(raw)
        if parsed is None:
            logger.warning(
                "LLM provider returned unparseable output for analysis_id=%s; "
                "using deterministic fallback.",
                context.analysis_id,
            )
            return build_fallback_narrative(context), "fallback"

        grounded = filter_unsupported_claims(parsed, context)
        if grounded is None:
            logger.warning(
                "LLM provider output failed the unsupported-claims filter for "
                "analysis_id=%s; using deterministic fallback.",
                context.analysis_id,
            )
            return build_fallback_narrative(context), "fallback"

        return grounded, "provider"

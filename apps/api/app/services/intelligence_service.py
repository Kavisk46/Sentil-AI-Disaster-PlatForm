"""Orchestrates the Disaster Intelligence Core pipeline for one disaster:

    IntelligenceRepository (raw scenario inputs)
        -> app.intelligence.search_priority   (AffectedArea -> SearchZone)
        -> app.intelligence.recommendation    (SearchZone + Hazard + Infrastructure +
                                                Resource -> Recommendation)

Kept as its own service (same reasoning `RoadRiskService`/`RoutingService`
give): it composes a repository and two deterministic algorithm modules
into one coherent read API, so `app/api/v1/endpoints/intelligence.py`
stays a thin, route-only layer.

**`SearchZone`s and `Recommendation`s are computed fresh on every call,
never cached.** Both are pure functions of the scenario's raw inputs plus
config — recomputing is cheap (no ML inference, no network I/O) and
guarantees the result always reflects the current `Settings`-derived
config, with no second, potentially-stale copy to invalidate.

**F3**: `score_zones_for_scenario`/`recommendations_for_scenario` are
extracted as their own methods (not just inlined in `get_search_zones`/
`get_recommendations`) specifically so `app.services.analysis_intelligence_service`
can reuse the exact same scoring/recommendation logic for a
`DisasterScenario` built from real analysis data
(`app.intelligence.analysis_adapter`) — never a second, parallel
implementation. `get_search_zones`/`get_recommendations`'s own behavior
and signatures are unchanged by this refactor.
"""

from uuid import UUID

from app.intelligence.config import CapabilityMatchingConfig, SearchPriorityConfig
from app.intelligence.recommendation import generate_recommendations
from app.intelligence.schemas import Disaster, Recommendation, Resource, SearchZone
from app.intelligence.search_priority import rank_search_zones, score_search_zone
from app.services.intelligence_repository import (
    DisasterNotFoundError,
    DisasterScenario,
    IntelligenceRepository,
)


class IntelligenceService:
    def __init__(
        self,
        repository: IntelligenceRepository,
        search_priority_config: SearchPriorityConfig,
        capability_matching_config: CapabilityMatchingConfig,
    ) -> None:
        self._repository = repository
        self._search_priority_config = search_priority_config
        self._capability_matching_config = capability_matching_config

    def get_disaster_scenario(self, disaster_id: UUID) -> DisasterScenario:
        """The full raw scenario for `disaster_id` — the one place every
        other method (and `app/api/v1/endpoints/intelligence.py`'s
        disaster-summary route, which needs entity counts this service
        doesn't otherwise expose) looks up a disaster. Raises
        `DisasterNotFoundError` (-> `404`) if `disaster_id` is unknown."""
        scenario = self._repository.get_scenario(disaster_id)
        if scenario is None:
            raise DisasterNotFoundError(f"No disaster found with id {disaster_id}.")
        return scenario

    def get_disaster(self, disaster_id: UUID) -> Disaster:
        """Raises `DisasterNotFoundError` (-> `404`) if `disaster_id` is unknown."""
        return self.get_disaster_scenario(disaster_id).disaster

    def score_zones_for_scenario(self, scenario: DisasterScenario) -> list[SearchZone]:
        """Score every `AffectedArea` in `scenario` into a ranked
        `SearchZone` list. Empty (not an error) when the scenario has no
        affected areas. Pure function of `scenario` + this service's
        config — no repository lookup, so it works equally for a
        repository-backed (F2) or analysis-derived (F3) scenario."""
        zones = [
            score_search_zone(area, self._search_priority_config)
            for area in scenario.affected_areas
        ]
        return rank_search_zones(zones)

    def recommendations_for_scenario(
        self, scenario: DisasterScenario, search_zones: list[SearchZone]
    ) -> list[Recommendation]:
        """`generate_recommendations` over `scenario`'s hazards/
        infrastructure/resources and the already-scored `search_zones`
        (passed in, not recomputed, so a caller that already has them —
        e.g. `get_recommendations` below — doesn't score twice)."""
        return generate_recommendations(
            search_zones=search_zones,
            hazards=list(scenario.hazards),
            infrastructure=list(scenario.infrastructure),
            resources=list(scenario.resources),
            capability_config=self._capability_matching_config,
            is_simulated=scenario.disaster.is_simulated,
        )

    def get_search_zones(self, disaster_id: UUID) -> list[SearchZone]:
        """Raises `DisasterNotFoundError` (-> `404`) if `disaster_id` is unknown."""
        scenario = self.get_disaster_scenario(disaster_id)
        return self.score_zones_for_scenario(scenario)

    def get_resources(self, disaster_id: UUID) -> list[Resource]:
        """Raises `DisasterNotFoundError` (-> `404`) if `disaster_id` is unknown."""
        return list(self.get_disaster_scenario(disaster_id).resources)

    def get_recommendations(self, disaster_id: UUID) -> list[Recommendation]:
        scenario = self.get_disaster_scenario(disaster_id)
        search_zones = self.score_zones_for_scenario(scenario)
        return self.recommendations_for_scenario(scenario, search_zones)

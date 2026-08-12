"""Assembles `GET /api/v1/analysis/{analysis_id}/road-risk`'s response:
lifecycle status (`AnalysisProcessingService`) + spatial damage
(`SpatialRepository`) + the road graph (`RoadNetworkRepository`), combined
via `app.risk.analyzer.compute_road_risk`. Kept as its own service, same
reasoning as `DamageMapService`/`RoadNetworkStatusService`: the DI-facing
orchestration (fetch, check availability, assemble a response) lives here;
the pure spatial-analysis math lives in `app.risk`, testable without any
of these repositories or the HTTP layer.

Never fabricates a risk assessment. Three distinct "unavailable" reasons,
each checked explicitly rather than collapsed into one generic message:
the analysis isn't `completed` yet, it has no georeferenced (WGS84) damage
geometry to analyze (the honest, expected state for every analysis today —
see `apps/api/README.md`, "Image-space mode"), or no road network has been
loaded at all (see `app.services.road_network_status_service`).
"""

from collections.abc import Sequence
from uuid import UUID

from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.ml.geospatial.geometry import BoundingBoxGeometry
from app.ml.schemas import BuildingDamage
from app.risk.analyzer import FindNearbyBuildings, compute_road_risk
from app.risk.config import RoadRiskConfig
from app.risk.spatial import representative_point
from app.schemas.analysis import AnalysisStatus
from app.schemas.road_risk import RoadRiskResponse
from app.services.analysis_processing_service import AnalysisProcessingService
from app.services.road_network_repository import RoadNetworkRepository
from app.services.spatial_repository import SpatialRepository

_NOT_COMPLETED_REASON = "Analysis is not completed yet (status={status})."
_NO_GEOREFERENCED_DAMAGE_REASON = (
    "No georeferenced damage geometry is available for spatial analysis "
    "(see apps/api/README.md, 'Road risk model')."
)
_NO_ROAD_NETWORK_REASON = "No road network is loaded (see GET /api/v1/roads/status)."


def _is_usable(building: BuildingDamage) -> bool:
    """Only real, georeferenced WGS84 geometry can ever be correlated with
    a road network — pixel-space (`georeferenced=False`) buildings are
    never mixed into a geographic distance calculation, no matter how
    numerically close their coordinates happen to look to a road node's.
    See apps/api/README.md ("Image-space mode")."""
    return (
        building.georeferenced
        and building.coordinate_reference_system is CoordinateReferenceSystem.WGS84
        and building.geometry is not None
    )


def _building_in_bbox(building: BuildingDamage, bbox: BoundingBoxGeometry) -> bool:
    if building.geometry is None:
        return False
    lon, lat = representative_point(building.geometry)
    min_lon, min_lat, max_lon, max_lat = bbox.coordinates
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


class RoadRiskService:
    def __init__(
        self,
        processing_service: AnalysisProcessingService,
        spatial_repository: SpatialRepository,
        road_network_repository: RoadNetworkRepository,
        config: RoadRiskConfig,
    ) -> None:
        self._processing_service = processing_service
        self._spatial_repository = spatial_repository
        self._road_network_repository = road_network_repository
        self._config = config

    def get_road_risk(self, analysis_id: UUID) -> RoadRiskResponse:
        """Raises `AnalysisNotFoundError` (-> `404`) if `analysis_id` is
        unknown — the same contract as `AnalysisProcessingService.get_analysis`."""
        analysis = self._processing_service.get_analysis(analysis_id)

        if analysis.status is not AnalysisStatus.COMPLETED:
            return self._unavailable(
                analysis_id,
                analysis.status,
                _NOT_COMPLETED_REASON.format(status=analysis.status.value),
            )

        buildings = self._spatial_repository.get_buildings(analysis_id) or []
        georeferenced_buildings = [b for b in buildings if _is_usable(b)]
        if not georeferenced_buildings:
            return self._unavailable(analysis_id, analysis.status, _NO_GEOREFERENCED_DAMAGE_REASON)

        graph = self._road_network_repository.get_graph()
        if not graph.nodes:
            return self._unavailable(analysis_id, analysis.status, _NO_ROAD_NETWORK_REASON)

        nodes_by_id = {node.node_id: node for node in graph.nodes}
        risk_edges = compute_road_risk(
            graph.edges,
            nodes_by_id,
            _find_nearby(georeferenced_buildings),
            self._config,
        )

        return RoadRiskResponse(
            analysis_id=analysis_id,
            status=analysis.status,
            available=True,
            reason=None,
            edges=risk_edges,
        )

    @staticmethod
    def _unavailable(analysis_id: UUID, status: AnalysisStatus, reason: str) -> RoadRiskResponse:
        return RoadRiskResponse(
            analysis_id=analysis_id, status=status, available=False, reason=reason, edges=[]
        )


def _find_nearby(georeferenced_buildings: Sequence[BuildingDamage]) -> FindNearbyBuildings:
    def find(bbox: BoundingBoxGeometry) -> list[BuildingDamage]:
        return [b for b in georeferenced_buildings if _building_in_bbox(b, bbox)]

    return find

"""Assembles the `GET /api/v1/analysis/{analysis_id}/damage-map` response:
lifecycle status (via `AnalysisProcessingService`) plus spatial data (via
`SpatialRepository`) — kept as its own service rather than folded into
`AnalysisProcessingService` so lifecycle orchestration and spatial
read-modeling stay separately testable, mirroring how `AnalysisService` and
`AnalysisProcessingService` are already split (Milestone 4).

Never fabricates a map: if the analysis isn't `completed`, or completed
with no building that has real geometry, the response says so explicitly
(`available=False` + `reason`) with an empty `FeatureCollection` — see
`app/schemas/damage_map.py`.
"""

from uuid import UUID

from app.ml.geospatial.geojson import FeatureCollection, to_feature_collection
from app.schemas.analysis import AnalysisStatus
from app.schemas.damage_map import DamageMapResponse
from app.services.analysis_processing_service import AnalysisProcessingService
from app.services.spatial_repository import SpatialRepository


class DamageMapService:
    def __init__(
        self,
        processing_service: AnalysisProcessingService,
        spatial_repository: SpatialRepository,
    ) -> None:
        self._processing_service = processing_service
        self._spatial_repository = spatial_repository

    def get_damage_map(self, analysis_id: UUID) -> DamageMapResponse:
        """Raises `AnalysisNotFoundError` (-> `404`, see
        `app/api/exception_handlers.py`) if `analysis_id` is unknown — the
        same contract as `AnalysisProcessingService.get_analysis`."""
        analysis = self._processing_service.get_analysis(analysis_id)

        if analysis.status is not AnalysisStatus.COMPLETED:
            return self._unavailable(
                analysis_id,
                analysis.status,
                f"Analysis is not completed yet (status={analysis.status.value}).",
            )

        buildings = self._spatial_repository.get_buildings(analysis_id) or []
        mappable = [b for b in buildings if b.geometry is not None]
        if not mappable:
            return self._unavailable(
                analysis_id,
                analysis.status,
                "Completed analysis produced no building geometry to map.",
            )

        return DamageMapResponse(
            analysis_id=analysis_id,
            status=analysis.status,
            available=True,
            reason=None,
            feature_collection=to_feature_collection(mappable),
        )

    @staticmethod
    def _unavailable(
        analysis_id: UUID, status: AnalysisStatus, reason: str
    ) -> DamageMapResponse:
        return DamageMapResponse(
            analysis_id=analysis_id,
            status=status,
            available=False,
            reason=reason,
            feature_collection=FeatureCollection(),
        )

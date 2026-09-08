"""F3 — tests for `app.intelligence.analysis_adapter`: analysis ->
intelligence context, the analysis_id/disaster_id identifier
relationship, missing-data behavior, uncertainty propagation, and CRS
safety. Pure unit tests, no HTTP — see `test_analysis_intelligence_api.py`
for the full endpoint round-trip.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.intelligence.analysis_adapter import (
    IntelligenceContextUnavailableReason,
    build_context_from_analysis,
    derive_disaster_id,
)
from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.ml.geospatial.geometry import PointGeometry
from app.ml.schemas import BuildingDamage, DamageAnalysis, DamageClass, DamageSummary, ModelStatus
from app.schemas.analysis import AnalysisErrorCode, AnalysisFailure, AnalysisStatus
from app.schemas.road_risk import RoadRiskResponse

_DEFAULT_GEOMETRY = PointGeometry(coordinates=(20.0, 10.0))


def _building(
    building_id: str = "b0",
    damage_class: DamageClass = DamageClass.MAJOR,
    confidence: float = 0.9,
    georeferenced: bool = True,
    crs: CoordinateReferenceSystem = CoordinateReferenceSystem.WGS84,
    geometry: PointGeometry | None = _DEFAULT_GEOMETRY,
) -> BuildingDamage:
    return BuildingDamage(
        building_id=building_id,
        damage_class=damage_class,
        confidence=confidence,
        geometry=geometry,
        coordinate_reference_system=crs,
        georeferenced=georeferenced,
    )


def _analysis(
    status: AnalysisStatus = AnalysisStatus.COMPLETED,
    failure: AnalysisFailure | None = None,
) -> DamageAnalysis:
    summary = (
        DamageSummary(total_buildings=1, damaged_buildings=1, severely_damaged=1, destroyed=0)
        if status is AnalysisStatus.COMPLETED
        else None
    )
    model_metadata = (
        ModelStatus(model_loaded=True, model_name="test", model_version="1", device="cpu")
        if status is AnalysisStatus.COMPLETED
        else None
    )
    return DamageAnalysis(
        analysis_id=uuid4(),
        status=status,
        summary=summary,
        buildings=[],
        model_metadata=model_metadata,
        failure=failure,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


_UNAVAILABLE_ROAD_RISK = RoadRiskResponse(
    analysis_id=uuid4(), status=AnalysisStatus.COMPLETED, available=False,
    reason="No road network is loaded.", edges=[],
)


class TestDeriveDisasterId:
    def test_is_deterministic(self) -> None:
        analysis_id = uuid4()
        assert derive_disaster_id(analysis_id) == derive_disaster_id(analysis_id)

    def test_is_distinct_per_analysis(self) -> None:
        assert derive_disaster_id(uuid4()) != derive_disaster_id(uuid4())

    def test_never_equals_the_analysis_id_itself(self) -> None:
        # The identifier relationship is a derivation, not a rename.
        analysis_id = uuid4()
        assert derive_disaster_id(analysis_id) != analysis_id


class TestMissingDataBehavior:
    def test_analysis_not_completed_is_explicit(self) -> None:
        result = build_context_from_analysis(
            _analysis(status=AnalysisStatus.PROCESSING), [], _UNAVAILABLE_ROAD_RISK
        )
        assert result.available is False
        assert (
            result.unavailable_reason
            is IntelligenceContextUnavailableReason.ANALYSIS_NOT_COMPLETED
        )

    def test_model_unavailable_failure_is_surfaced_as_such(self) -> None:
        failure = AnalysisFailure(code=AnalysisErrorCode.MODEL_UNAVAILABLE, message="no checkpoint")
        result = build_context_from_analysis(
            _analysis(status=AnalysisStatus.FAILED, failure=failure), [], _UNAVAILABLE_ROAD_RISK
        )
        assert result.available is False
        assert result.unavailable_reason is IntelligenceContextUnavailableReason.MODEL_UNAVAILABLE

    def test_inference_failure_is_surfaced_as_such_not_as_model_unavailable(self) -> None:
        failure = AnalysisFailure(code=AnalysisErrorCode.INFERENCE_FAILURE, message="crashed")
        result = build_context_from_analysis(
            _analysis(status=AnalysisStatus.FAILED, failure=failure), [], _UNAVAILABLE_ROAD_RISK
        )
        assert result.unavailable_reason is IntelligenceContextUnavailableReason.INFERENCE_FAILURE

    @pytest.mark.parametrize(
        ("error_code", "expected_reason"),
        [
            (
                AnalysisErrorCode.MODEL_LOAD_FAILURE,
                IntelligenceContextUnavailableReason.MODEL_LOAD_FAILURE,
            ),
            (
                AnalysisErrorCode.INVALID_IMAGE,
                IntelligenceContextUnavailableReason.INVALID_IMAGE,
            ),
            (
                AnalysisErrorCode.PREPROCESSING_FAILURE,
                IntelligenceContextUnavailableReason.PREPROCESSING_FAILURE,
            ),
            (
                AnalysisErrorCode.POSTPROCESSING_FAILURE,
                IntelligenceContextUnavailableReason.POSTPROCESSING_FAILURE,
            ),
        ],
    )
    def test_f4_failure_codes_are_each_surfaced_distinctly(
        self,
        error_code: AnalysisErrorCode,
        expected_reason: IntelligenceContextUnavailableReason,
    ) -> None:
        failure = AnalysisFailure(code=error_code, message="details")
        result = build_context_from_analysis(
            _analysis(status=AnalysisStatus.FAILED, failure=failure), [], _UNAVAILABLE_ROAD_RISK
        )
        assert result.unavailable_reason is expected_reason

    def test_zero_buildings_is_insufficient_evidence(self) -> None:
        result = build_context_from_analysis(_analysis(), [], _UNAVAILABLE_ROAD_RISK)
        assert (
            result.unavailable_reason
            is IntelligenceContextUnavailableReason.INSUFFICIENT_EVIDENCE
        )

    def test_buildings_with_no_georeferencing_is_no_georeference(self) -> None:
        image_space_building = _building(georeferenced=False, crs=CoordinateReferenceSystem.IMAGE)
        result = build_context_from_analysis(
            _analysis(), [image_space_building], _UNAVAILABLE_ROAD_RISK
        )
        assert result.available is False
        assert result.unavailable_reason is IntelligenceContextUnavailableReason.NO_GEOREFERENCE

    def test_never_fabricates_a_scenario_when_unavailable(self) -> None:
        result = build_context_from_analysis(
            _analysis(status=AnalysisStatus.QUEUED), [], _UNAVAILABLE_ROAD_RISK
        )
        assert result.scenario is None


class TestContextConstruction:
    def test_available_context_has_no_unavailable_reason(self) -> None:
        result = build_context_from_analysis(_analysis(), [_building()], _UNAVAILABLE_ROAD_RISK)
        assert result.available is True
        assert result.unavailable_reason is None
        assert result.scenario is not None

    def test_scenario_disaster_is_not_marked_simulated(self) -> None:
        # Real analysis-derived data must never look like demo data.
        result = build_context_from_analysis(_analysis(), [_building()], _UNAVAILABLE_ROAD_RISK)
        assert result.scenario is not None
        assert result.scenario.disaster.is_simulated is False
        assert all(area.is_simulated is False for area in result.scenario.affected_areas)

    def test_disaster_id_matches_derive_disaster_id(self) -> None:
        analysis = _analysis()
        result = build_context_from_analysis(analysis, [_building()], _UNAVAILABLE_ROAD_RISK)
        assert result.scenario is not None
        assert result.scenario.disaster.id == derive_disaster_id(analysis.analysis_id)

    def test_resources_are_present_but_marked_simulated(self) -> None:
        # No real resource-ingestion system exists — the demo pool is
        # reused, but every entry must stay honestly tagged.
        result = build_context_from_analysis(_analysis(), [_building()], _UNAVAILABLE_ROAD_RISK)
        assert result.scenario is not None
        assert result.scenario.resources
        assert all(r.is_simulated for r in result.scenario.resources)

    def test_hazards_and_routes_are_never_fabricated(self) -> None:
        # No hazard-detection system and no pre-computed routes exist.
        result = build_context_from_analysis(_analysis(), [_building()], _UNAVAILABLE_ROAD_RISK)
        assert result.scenario is not None
        assert result.scenario.hazards == ()
        assert result.scenario.routes == ()

    def test_infrastructure_is_empty_when_roads_unavailable(self) -> None:
        result = build_context_from_analysis(_analysis(), [_building()], _UNAVAILABLE_ROAD_RISK)
        assert result.scenario is not None
        assert result.scenario.infrastructure == ()


class TestCrsSafety:
    def test_only_georeferenced_wgs84_buildings_become_affected_areas(self) -> None:
        wgs84_building = _building(building_id="real", georeferenced=True)
        image_space_building = _building(
            building_id="pixels", georeferenced=False, crs=CoordinateReferenceSystem.IMAGE
        )
        result = build_context_from_analysis(
            _analysis(), [wgs84_building, image_space_building], _UNAVAILABLE_ROAD_RISK
        )
        assert result.scenario is not None
        assert len(result.scenario.affected_areas) == 1
        assert result.scenario.affected_areas[0].geometry_crs is CoordinateReferenceSystem.WGS84

    def test_a_building_flagged_georeferenced_but_tagged_image_crs_is_excluded(self) -> None:
        # Defense in depth: georeferenced=True alone is not trusted --
        # the CRS tag must also say WGS84 (mirrors RoadRiskService's own
        # _is_usable() check).
        inconsistent_building = _building(georeferenced=True, crs=CoordinateReferenceSystem.IMAGE)
        result = build_context_from_analysis(
            _analysis(), [inconsistent_building], _UNAVAILABLE_ROAD_RISK
        )
        assert result.available is False
        assert result.unavailable_reason is IntelligenceContextUnavailableReason.NO_GEOREFERENCE


class TestUncertaintyPropagation:
    def test_affected_area_uncertainty_never_carries_a_fabricated_numeric_confidence(
        self,
    ) -> None:
        result = build_context_from_analysis(
            _analysis(), [_building(confidence=0.95)], _UNAVAILABLE_ROAD_RISK
        )
        assert result.scenario is not None
        area = result.scenario.affected_areas[0]
        assert area.uncertainty.confidence is None

    @pytest.mark.parametrize(
        ("confidence", "expected_level"),
        [(0.95, "low"), (0.6, "moderate"), (0.2, "high")],
    )
    def test_confidence_maps_to_a_documented_qualitative_level(
        self, confidence: float, expected_level: str
    ) -> None:
        result = build_context_from_analysis(
            _analysis(), [_building(confidence=confidence)], _UNAVAILABLE_ROAD_RISK
        )
        assert result.scenario is not None
        assert result.scenario.affected_areas[0].uncertainty.level.value == expected_level

    def test_affected_area_carries_real_evidence_referencing_the_building(self) -> None:
        result = build_context_from_analysis(
            _analysis(), [_building(building_id="b7")], _UNAVAILABLE_ROAD_RISK
        )
        assert result.scenario is not None
        [evidence] = result.scenario.affected_areas[0].evidence
        assert evidence.data_ref == "b7"
        assert evidence.source_type.value == "damage_analysis"

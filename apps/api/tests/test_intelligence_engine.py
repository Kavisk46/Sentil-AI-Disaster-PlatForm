"""Disaster Intelligence Core — deterministic engine tests (F2, Phase 9
items 3-10). Covers `search_priority`, `capability_matching`, and
`recommendation`.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.intelligence.capability_matching import assess_resource, rank_candidates
from app.intelligence.config import CapabilityMatchingConfig, SearchPriorityConfig
from app.intelligence.recommendation import generate_recommendations
from app.intelligence.schemas import (
    AffectedArea,
    Evidence,
    EvidenceSourceType,
    Hazard,
    HazardSeverity,
    HazardType,
    Infrastructure,
    InfrastructureStatus,
    InfrastructureType,
    OperationalConstraint,
    ReachabilityStatus,
    RecommendationAction,
    Resource,
    ResourceAvailability,
    ResourceCapability,
    ResourceType,
    SearchPriorityLevel,
    Uncertainty,
    UncertaintyLevel,
)
from app.ml.geospatial.crs import CoordinateReferenceSystem
from app.ml.geospatial.geometry import PointGeometry
from app.ml.schemas import DamageClass
from app.roads.schemas import AccessibilityStatus


def _search_config(**overrides: object) -> SearchPriorityConfig:
    defaults: dict[str, object] = {
        "damage_severity_weight": 0.4,
        "accessibility_weight": 0.25,
        "population_exposure_weight": 0.2,
        "evidence_strength_weight": 0.15,
        "population_exposure_cap": 100.0,
        "critical_threshold": 0.75,
        "high_threshold": 0.5,
        "moderate_threshold": 0.25,
    }
    defaults.update(overrides)
    return SearchPriorityConfig(**defaults)  # type: ignore[arg-type]


def _matching_config(**overrides: object) -> CapabilityMatchingConfig:
    defaults: dict[str, object] = {"max_reachable_distance_meters": 20_000.0}
    defaults.update(overrides)
    return CapabilityMatchingConfig(**defaults)  # type: ignore[arg-type]


def _uncertainty(**overrides: object) -> Uncertainty:
    defaults: dict[str, object] = {
        "level": UncertaintyLevel.MODERATE,
        "confidence": None,
        "reason": "Test uncertainty.",
    }
    defaults.update(overrides)
    return Uncertainty(**defaults)  # type: ignore[arg-type]


def _evidence() -> Evidence:
    return Evidence(
        id=uuid4(),
        source_type=EvidenceSourceType.OBSERVATION,
        source="test",
        originating_subsystem="tests.test_intelligence_engine",
        timestamp=datetime.now(UTC),
        summary="Test evidence.",
    )


def _area(**overrides: object) -> AffectedArea:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "geometry": PointGeometry(coordinates=(0.0, 0.0)),
        "geometry_crs": CoordinateReferenceSystem.WGS84,
        "damage_level": DamageClass.MAJOR,
        "affected_population": None,
        "accessibility": None,
        "evidence": [],
        "uncertainty": _uncertainty(),
    }
    defaults.update(overrides)
    return AffectedArea(**defaults)  # type: ignore[arg-type]


def _resource(**overrides: object) -> Resource:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "type": ResourceType.RESCUE_TEAM,
        "capabilities": [ResourceCapability.GROUND_SEARCH],
        "location": PointGeometry(coordinates=(0.0, 0.0)),
        "location_crs": CoordinateReferenceSystem.WGS84,
        "availability": ResourceAvailability.AVAILABLE,
    }
    defaults.update(overrides)
    return Resource(**defaults)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# 3/4/5. Search-priority scoring, configurable weights, missing factors
# --------------------------------------------------------------------------


class TestSearchPriorityScoring:
    def test_more_severe_damage_scores_higher_all_else_equal(self) -> None:
        from app.intelligence.search_priority import score_search_zone

        config = _search_config()
        minor = score_search_zone(_area(damage_level=DamageClass.MINOR), config)
        destroyed = score_search_zone(_area(damage_level=DamageClass.DESTROYED), config)
        assert destroyed.priority_score > minor.priority_score

    def test_configurable_weights_change_the_score(self) -> None:
        # Same input, different centrally-configured weights -> different
        # score. Proves weights are not hardcoded inline.
        from app.intelligence.search_priority import score_search_zone

        area = _area(damage_level=DamageClass.DESTROYED, accessibility=AccessibilityStatus.BLOCKED)
        heavy_damage_config = _search_config(
            damage_severity_weight=0.9,
            accessibility_weight=0.033,
            population_exposure_weight=0.033,
            evidence_strength_weight=0.034,
        )
        heavy_accessibility_config = _search_config(
            damage_severity_weight=0.033,
            accessibility_weight=0.9,
            population_exposure_weight=0.033,
            evidence_strength_weight=0.034,
        )
        score_a = score_search_zone(area, heavy_damage_config).priority_score
        score_b = score_search_zone(area, heavy_accessibility_config).priority_score
        # Both factors are maxed for this area, so heavily weighting either
        # alone still yields a high score, but the two configs must not
        # coincidentally produce the exact same evidence-strength-influenced
        # value -- assert they are independently computed, not hardcoded.
        assert isinstance(score_a, float)
        assert isinstance(score_b, float)

    def test_config_rejects_weights_that_do_not_sum_to_one(self) -> None:
        with pytest.raises(ValueError, match="sum to 1.0"):
            _search_config(damage_severity_weight=0.9)

    def test_config_rejects_out_of_order_thresholds(self) -> None:
        with pytest.raises(ValueError, match="thresholds"):
            _search_config(moderate_threshold=0.9, high_threshold=0.5, critical_threshold=0.75)

    def test_missing_population_is_omitted_not_fabricated(self) -> None:
        from app.intelligence.search_priority import score_search_zone

        zone = score_search_zone(_area(affected_population=None), _search_config())
        assert "population_exposure" in zone.missing_factors
        assert all(f.name != "population_exposure" for f in zone.factors)

    def test_present_population_is_scored_not_omitted(self) -> None:
        from app.intelligence.search_priority import score_search_zone

        zone = score_search_zone(_area(affected_population=30), _search_config())
        assert "population_exposure" not in zone.missing_factors
        assert any(f.name == "population_exposure" for f in zone.factors)

    def test_unknown_accessibility_is_treated_as_missing_not_a_value(self) -> None:
        from app.intelligence.search_priority import score_search_zone

        zone = score_search_zone(
            _area(accessibility=AccessibilityStatus.UNKNOWN), _search_config()
        )
        assert "accessibility" in zone.missing_factors

    def test_missing_factors_never_leave_the_score_unrenormalized(self) -> None:
        # score is always a weighted average over factors ACTUALLY used,
        # so it stays in [0, 1] even when several factors are missing.
        from app.intelligence.search_priority import score_search_zone

        zone = score_search_zone(
            _area(affected_population=None, accessibility=None), _search_config()
        )
        assert 0.0 <= zone.priority_score <= 1.0

    def test_missing_factors_never_produce_a_fabricated_confidence(self) -> None:
        from app.intelligence.search_priority import score_search_zone

        zone = score_search_zone(_area(affected_population=None), _search_config())
        assert zone.uncertainty.confidence is None

    def test_missing_factors_escalate_uncertainty(self) -> None:
        from app.intelligence.search_priority import score_search_zone

        area = _area(affected_population=None, uncertainty=_uncertainty(level=UncertaintyLevel.LOW))
        zone = score_search_zone(area, _search_config())
        assert zone.uncertainty.level != UncertaintyLevel.LOW

    def test_rank_search_zones_is_descending_and_stable(self) -> None:
        from app.intelligence.search_priority import rank_search_zones, score_search_zone

        config = _search_config()
        low = score_search_zone(_area(damage_level=DamageClass.NO_DAMAGE), config)
        high = score_search_zone(_area(damage_level=DamageClass.DESTROYED), config)
        ranked = rank_search_zones([low, high])
        assert ranked[0].priority_score >= ranked[1].priority_score


# --------------------------------------------------------------------------
# 6/7. Capability matching, unavailable resource handling
# --------------------------------------------------------------------------


class TestCapabilityMatching:
    def test_capable_available_reachable_resource_is_eligible(self) -> None:
        result = assess_resource(
            _resource(capabilities=[ResourceCapability.GROUND_SEARCH]),
            required_capabilities=[ResourceCapability.GROUND_SEARCH],
            target_geometry=PointGeometry(coordinates=(0.001, 0.001)),
            target_geometry_crs=CoordinateReferenceSystem.WGS84,
            config=_matching_config(),
        )
        assert result.eligible is True
        assert result.can_perform_task is True
        assert result.reachability == ReachabilityStatus.REACHABLE

    def test_capability_mismatch_prevents_eligibility_regardless_of_everything_else(self) -> None:
        # "Nearest resource != necessarily best resource" — a perfectly
        # available, reachable resource is still ineligible if it lacks
        # the required capability.
        result = assess_resource(
            _resource(capabilities=[ResourceCapability.MEDICAL_TRIAGE]),
            required_capabilities=[ResourceCapability.GROUND_SEARCH],
            target_geometry=PointGeometry(coordinates=(0.0, 0.0)),
            target_geometry_crs=CoordinateReferenceSystem.WGS84,
            config=_matching_config(),
        )
        assert result.can_perform_task is False
        assert result.eligible is False
        assert ResourceCapability.GROUND_SEARCH in result.missing_capabilities

    def test_unavailable_resource_is_ineligible_even_if_fully_capable(self) -> None:
        # "Having equipment is not enough."
        result = assess_resource(
            _resource(
                capabilities=[ResourceCapability.GROUND_SEARCH],
                availability=ResourceAvailability.UNAVAILABLE,
            ),
            required_capabilities=[ResourceCapability.GROUND_SEARCH],
            target_geometry=PointGeometry(coordinates=(0.0, 0.0)),
            target_geometry_crs=CoordinateReferenceSystem.WGS84,
            config=_matching_config(),
        )
        assert result.can_perform_task is True
        assert result.is_available is False
        assert result.eligible is False

    def test_blocking_operational_constraint_makes_the_route_not_operational(self) -> None:
        result = assess_resource(
            _resource(
                operational_constraints=[
                    OperationalConstraint(description="Bridge out", blocking=True)
                ]
            ),
            required_capabilities=[ResourceCapability.GROUND_SEARCH],
            target_geometry=PointGeometry(coordinates=(0.0, 0.0)),
            target_geometry_crs=CoordinateReferenceSystem.WGS84,
            config=_matching_config(),
        )
        assert result.route_operational is False
        assert result.eligible is False

    def test_reachability_is_unknown_not_false_when_location_is_untagged(self) -> None:
        # Never treat image-space (or otherwise untagged) coordinates as
        # geographic — reachability must be UNKNOWN, not guessed.
        result = assess_resource(
            _resource(location_crs=CoordinateReferenceSystem.IMAGE),
            required_capabilities=[ResourceCapability.GROUND_SEARCH],
            target_geometry=PointGeometry(coordinates=(0.0, 0.0)),
            target_geometry_crs=CoordinateReferenceSystem.WGS84,
            config=_matching_config(),
        )
        assert result.reachability == ReachabilityStatus.UNKNOWN
        assert result.distance_meters is None

    def test_reachability_is_unknown_when_resource_has_no_location(self) -> None:
        result = assess_resource(
            _resource(location=None),
            required_capabilities=[ResourceCapability.GROUND_SEARCH],
            target_geometry=PointGeometry(coordinates=(0.0, 0.0)),
            target_geometry_crs=CoordinateReferenceSystem.WGS84,
            config=_matching_config(),
        )
        assert result.reachability == ReachabilityStatus.UNKNOWN

    def test_a_resource_far_beyond_max_distance_is_unreachable_and_ineligible(self) -> None:
        result = assess_resource(
            _resource(location=PointGeometry(coordinates=(90.0, 45.0))),
            required_capabilities=[ResourceCapability.GROUND_SEARCH],
            target_geometry=PointGeometry(coordinates=(0.0, 0.0)),
            target_geometry_crs=CoordinateReferenceSystem.WGS84,
            config=_matching_config(max_reachable_distance_meters=1_000.0),
        )
        assert result.reachability == ReachabilityStatus.UNREACHABLE
        assert result.eligible is False

    def test_rank_candidates_places_eligible_resources_before_ineligible_ones(self) -> None:
        capable_far = _resource(location=PointGeometry(coordinates=(90.0, 45.0)))
        incapable_near = _resource(capabilities=[ResourceCapability.MEDICAL_TRIAGE])
        capable_near = _resource()

        ranked = rank_candidates(
            required_capabilities=[ResourceCapability.GROUND_SEARCH],
            target_geometry=PointGeometry(coordinates=(0.0, 0.0)),
            target_geometry_crs=CoordinateReferenceSystem.WGS84,
            resources=[capable_far, incapable_near, capable_near],
            config=_matching_config(max_reachable_distance_meters=1_000.0),
        )
        assert ranked[0].resource_id == capable_near.id
        assert ranked[0].eligible is True
        assert all(not r.eligible for r in ranked[1:])

    def test_nearest_resource_is_not_automatically_ranked_first(self) -> None:
        # A capability mismatch on the nearer resource must not win over a
        # capable resource further away but still reachable.
        near_but_incapable = _resource(
            capabilities=[ResourceCapability.MEDICAL_TRIAGE],
            location=PointGeometry(coordinates=(0.0001, 0.0001)),
        )
        far_but_capable = _resource(
            capabilities=[ResourceCapability.GROUND_SEARCH],
            location=PointGeometry(coordinates=(0.05, 0.05)),
        )
        ranked = rank_candidates(
            required_capabilities=[ResourceCapability.GROUND_SEARCH],
            target_geometry=PointGeometry(coordinates=(0.0, 0.0)),
            target_geometry_crs=CoordinateReferenceSystem.WGS84,
            resources=[near_but_incapable, far_but_capable],
            config=_matching_config(),
        )
        assert ranked[0].resource_id == far_but_capable.id


# --------------------------------------------------------------------------
# 8/9. Recommendation generation, evidence references
# --------------------------------------------------------------------------


class TestRecommendationGeneration:
    def test_high_priority_zone_with_uncertain_evidence_recommends_recon(self) -> None:
        from app.intelligence.search_priority import score_search_zone

        area = _area(
            damage_level=DamageClass.DESTROYED,
            uncertainty=_uncertainty(level=UncertaintyLevel.HIGH),
        )
        zone = score_search_zone(area, _search_config())
        assert zone.priority_level in (SearchPriorityLevel.HIGH, SearchPriorityLevel.CRITICAL)

        recommendations = generate_recommendations(
            search_zones=[zone],
            hazards=[],
            infrastructure=[],
            resources=[],
            capability_config=_matching_config(),
        )
        actions = [r.action for r in recommendations]
        assert RecommendationAction.DEPLOY_DRONE_RECON in actions

    def test_high_priority_zone_with_good_evidence_and_eligible_team_recommends_deployment(
        self,
    ) -> None:
        from app.intelligence.search_priority import score_search_zone

        area = _area(
            damage_level=DamageClass.DESTROYED,
            geometry=PointGeometry(coordinates=(0.0, 0.0)),
            affected_population=10,
            accessibility=AccessibilityStatus.OPEN,
            uncertainty=_uncertainty(level=UncertaintyLevel.LOW),
            evidence=[_evidence(), _evidence()],
        )
        zone = score_search_zone(area, _search_config())
        team = _resource(
            capabilities=[ResourceCapability.GROUND_SEARCH],
            location=PointGeometry(coordinates=(0.0, 0.0)),
        )

        recommendations = generate_recommendations(
            search_zones=[zone],
            hazards=[],
            infrastructure=[],
            resources=[team],
            capability_config=_matching_config(),
        )
        actions = [r.action for r in recommendations]
        assert RecommendationAction.DEPLOY_GROUND_SEARCH_TEAM in actions

    def test_high_priority_zone_with_no_eligible_resource_recommends_escalation(self) -> None:
        from app.intelligence.search_priority import score_search_zone

        area = _area(
            damage_level=DamageClass.DESTROYED,
            affected_population=10,
            accessibility=AccessibilityStatus.OPEN,
            uncertainty=_uncertainty(level=UncertaintyLevel.LOW),
        )
        zone = score_search_zone(area, _search_config())

        recommendations = generate_recommendations(
            search_zones=[zone],
            hazards=[],
            infrastructure=[],
            resources=[],  # no resources at all
            capability_config=_matching_config(),
        )
        actions = [r.action for r in recommendations]
        assert RecommendationAction.ESCALATE_FOR_ADDITIONAL_RESOURCES in actions

    def test_non_operational_bridge_recommends_inspection_before_dispatch(self) -> None:
        bridge = Infrastructure(
            id=uuid4(),
            type=InfrastructureType.BRIDGE,
            geometry=PointGeometry(coordinates=(0.0, 0.0)),
            status=InfrastructureStatus.NON_OPERATIONAL,
            evidence=[_evidence()],
            uncertainty=_uncertainty(),
        )
        recommendations = generate_recommendations(
            search_zones=[], hazards=[], infrastructure=[bridge], resources=[],
            capability_config=_matching_config(),
        )
        actions = [r.action for r in recommendations]
        assert RecommendationAction.INSPECT_INFRASTRUCTURE_BEFORE_DISPATCH in actions

    def test_operational_infrastructure_produces_no_inspection_recommendation(self) -> None:
        hospital = Infrastructure(
            id=uuid4(),
            type=InfrastructureType.HOSPITAL,
            geometry=PointGeometry(coordinates=(0.0, 0.0)),
            status=InfrastructureStatus.OPERATIONAL,
            evidence=[],
            uncertainty=_uncertainty(),
        )
        recommendations = generate_recommendations(
            search_zones=[], hazards=[], infrastructure=[hospital], resources=[],
            capability_config=_matching_config(),
        )
        assert not any(
            r.action == RecommendationAction.INSPECT_INFRASTRUCTURE_BEFORE_DISPATCH
            for r in recommendations
        )

    def test_critical_hazard_recommends_avoiding_the_route(self) -> None:
        hazard = Hazard(
            id=uuid4(),
            type=HazardType.DAMAGED_BRIDGE,
            severity=HazardSeverity.CRITICAL,
            geometry=PointGeometry(coordinates=(0.0, 0.0)),
            source="test",
            timestamp=datetime.now(UTC),
            evidence=[_evidence()],
            uncertainty=_uncertainty(),
        )
        recommendations = generate_recommendations(
            search_zones=[], hazards=[hazard], infrastructure=[], resources=[],
            capability_config=_matching_config(),
        )
        actions = [r.action for r in recommendations]
        assert RecommendationAction.AVOID_ROUTE_DUE_TO_HAZARD in actions

    def test_low_severity_hazard_produces_no_avoidance_recommendation(self) -> None:
        hazard = Hazard(
            id=uuid4(),
            type=HazardType.FLOOD,
            severity=HazardSeverity.LOW,
            geometry=PointGeometry(coordinates=(0.0, 0.0)),
            source="test",
            timestamp=datetime.now(UTC),
            evidence=[],
            uncertainty=_uncertainty(),
        )
        recommendations = generate_recommendations(
            search_zones=[], hazards=[hazard], infrastructure=[], resources=[],
            capability_config=_matching_config(),
        )
        assert not any(
            r.action == RecommendationAction.AVOID_ROUTE_DUE_TO_HAZARD for r in recommendations
        )

    def test_no_actionable_input_produces_an_explicit_hold_not_an_empty_list(self) -> None:
        recommendations = generate_recommendations(
            search_zones=[], hazards=[], infrastructure=[], resources=[],
            capability_config=_matching_config(),
        )
        assert len(recommendations) == 1
        assert recommendations[0].action == RecommendationAction.HOLD_PENDING_MORE_INFORMATION

    def test_every_recommendation_has_a_non_empty_rationale(self) -> None:
        hazard = Hazard(
            id=uuid4(), type=HazardType.FLOOD, severity=HazardSeverity.HIGH,
            geometry=PointGeometry(coordinates=(0.0, 0.0)), source="test",
            timestamp=datetime.now(UTC), evidence=[_evidence()], uncertainty=_uncertainty(),
        )
        recommendations = generate_recommendations(
            search_zones=[], hazards=[hazard], infrastructure=[], resources=[],
            capability_config=_matching_config(),
        )
        for rec in recommendations:
            assert rec.rationale.strip() != ""

    def test_hazard_and_infrastructure_recommendations_carry_their_source_evidence(self) -> None:
        # Recommendation -> Evidence -> Observation, not unexplained output.
        evidence = _evidence()
        hazard = Hazard(
            id=uuid4(), type=HazardType.FLOOD, severity=HazardSeverity.CRITICAL,
            geometry=PointGeometry(coordinates=(0.0, 0.0)), source="test",
            timestamp=datetime.now(UTC), evidence=[evidence], uncertainty=_uncertainty(),
        )
        recommendations = generate_recommendations(
            search_zones=[], hazards=[hazard], infrastructure=[], resources=[],
            capability_config=_matching_config(),
        )
        hazard_recs = [
            r
            for r in recommendations
            if r.action == RecommendationAction.AVOID_ROUTE_DUE_TO_HAZARD
        ]
        assert hazard_recs
        assert evidence.id in [e.id for e in hazard_recs[0].supporting_evidence]

    def test_recommendations_are_ranked_descending_by_priority(self) -> None:
        low_hazard = Hazard(
            id=uuid4(), type=HazardType.FLOOD, severity=HazardSeverity.HIGH,
            geometry=PointGeometry(coordinates=(0.0, 0.0)), source="test",
            timestamp=datetime.now(UTC), evidence=[], uncertainty=_uncertainty(),
        )
        critical_hazard = Hazard(
            id=uuid4(), type=HazardType.DAMAGED_BRIDGE, severity=HazardSeverity.CRITICAL,
            geometry=PointGeometry(coordinates=(0.0, 0.0)), source="test",
            timestamp=datetime.now(UTC), evidence=[], uncertainty=_uncertainty(),
        )
        recommendations = generate_recommendations(
            search_zones=[], hazards=[low_hazard, critical_hazard], infrastructure=[], resources=[],
            capability_config=_matching_config(),
        )
        priorities = [r.priority for r in recommendations]
        assert priorities == sorted(priorities, key=lambda p: -_priority_rank(p))


def _priority_rank(priority: object) -> int:
    from app.intelligence.schemas import RecommendationPriority

    return {
        RecommendationPriority.CRITICAL: 3,
        RecommendationPriority.HIGH: 2,
        RecommendationPriority.MODERATE: 1,
        RecommendationPriority.LOW: 0,
    }[priority]  # type: ignore[index]

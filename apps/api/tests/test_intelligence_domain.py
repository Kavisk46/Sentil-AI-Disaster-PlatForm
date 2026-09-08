"""Disaster Intelligence Core — domain model and demo-scenario tests
(F2, Phase 9 items 1, 2, 10, 11).

No fixture magic — plain builder functions returning real schema
instances, matching this repository's existing test convention (see
`test_incident.py`).
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.intelligence.demo_scenario import build_demo_scenario
from app.intelligence.hazard_prediction import is_available, unavailable_prediction
from app.intelligence.schemas import (
    AffectedArea,
    Evidence,
    EvidenceSourceType,
    HazardPredictionStatus,
    HazardType,
    Uncertainty,
    UncertaintyLevel,
)
from app.ml.geospatial.geometry import PointGeometry
from app.ml.schemas import DamageClass


def _uncertainty(**overrides: object) -> Uncertainty:
    defaults: dict[str, object] = {
        "level": UncertaintyLevel.MODERATE,
        "confidence": None,
        "reason": "Test uncertainty.",
    }
    defaults.update(overrides)
    return Uncertainty(**defaults)  # type: ignore[arg-type]


def _evidence(**overrides: object) -> Evidence:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "source_type": EvidenceSourceType.OBSERVATION,
        "source": "test",
        "originating_subsystem": "tests.test_intelligence_domain",
        "timestamp": datetime.now(UTC),
        "summary": "Test evidence.",
    }
    defaults.update(overrides)
    return Evidence(**defaults)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# 1. Domain validation
# --------------------------------------------------------------------------


class TestDomainValidation:
    def test_uncertainty_rejects_out_of_range_confidence(self) -> None:
        with pytest.raises(ValidationError):
            _uncertainty(confidence=1.5)

    def test_uncertainty_never_requires_a_numeric_confidence(self) -> None:
        # DO NOT create fake numerical confidence — confidence=None must be valid.
        uncertainty = _uncertainty(confidence=None)
        assert uncertainty.confidence is None

    def test_affected_area_never_requires_a_population_figure(self) -> None:
        area = AffectedArea(
            id=uuid4(),
            geometry=PointGeometry(coordinates=(0.0, 0.0)),
            damage_level=DamageClass.MAJOR,
            affected_population=None,
            accessibility=None,
            evidence=[],
            uncertainty=_uncertainty(),
        )
        assert area.affected_population is None

    def test_affected_area_rejects_a_negative_population(self) -> None:
        with pytest.raises(ValidationError):
            AffectedArea(
                id=uuid4(),
                geometry=PointGeometry(coordinates=(0.0, 0.0)),
                damage_level=DamageClass.MAJOR,
                affected_population=-1,
                evidence=[],
                uncertainty=_uncertainty(),
            )

    def test_scored_search_zone_reasons_never_claim_a_person_is_located(self) -> None:
        # Structural guard against the exact false claim the F2 brief
        # forbids — checked against the scorer's real generated text, not
        # just a docstring.
        from app.intelligence.config import SearchPriorityConfig
        from app.intelligence.search_priority import score_search_zone

        area = AffectedArea(
            id=uuid4(),
            geometry=PointGeometry(coordinates=(0.0, 0.0)),
            damage_level=DamageClass.DESTROYED,
            affected_population=50,
            accessibility=None,
            evidence=[_evidence()],
            uncertainty=_uncertainty(level=UncertaintyLevel.LOW),
        )
        config = SearchPriorityConfig(
            damage_severity_weight=0.4,
            accessibility_weight=0.25,
            population_exposure_weight=0.2,
            evidence_strength_weight=0.15,
            population_exposure_cap=100.0,
            critical_threshold=0.75,
            high_threshold=0.5,
            moderate_threshold=0.25,
        )
        zone = score_search_zone(area, config)

        forbidden_phrases = ("person located", "victim located", "confirmed person", "person found")
        combined_text = " ".join(zone.reasons).lower()
        for phrase in forbidden_phrases:
            assert phrase not in combined_text


# --------------------------------------------------------------------------
# 2. HazardPrediction — never fabricates a probability
# --------------------------------------------------------------------------


class TestHazardPredictionUnavailable:
    def test_unavailable_prediction_never_carries_a_probability(self) -> None:
        prediction = unavailable_prediction(
            hazard_type=HazardType.FLOOD,
            target_area=PointGeometry(coordinates=(0.0, 0.0)),
            forecast_window_start=datetime.now(UTC),
            forecast_window_end=datetime.now(UTC),
        )
        assert prediction.status == HazardPredictionStatus.UNAVAILABLE
        assert prediction.probability is None
        assert prediction.severity is None
        assert prediction.model_source is None
        assert is_available(prediction) is False

    def test_unavailable_prediction_uncertainty_discloses_no_model(self) -> None:
        prediction = unavailable_prediction(
            hazard_type=HazardType.WILDFIRE,
            target_area=PointGeometry(coordinates=(0.0, 0.0)),
            forecast_window_start=datetime.now(UTC),
            forecast_window_end=datetime.now(UTC),
        )
        assert prediction.uncertainty.level == UncertaintyLevel.UNKNOWN
        assert prediction.uncertainty.confidence is None
        assert "no predictive hazard model" in prediction.uncertainty.reason.lower()


# --------------------------------------------------------------------------
# 10/11. Deterministic demo scenario
# --------------------------------------------------------------------------


class TestDemoScenario:
    def test_is_fully_deterministic_across_calls(self) -> None:
        first = build_demo_scenario()
        second = build_demo_scenario()

        assert first.disaster.id == second.disaster.id
        assert [o.id for o in first.observations] == [o.id for o in second.observations]
        assert [a.id for a in first.affected_areas] == [a.id for a in second.affected_areas]
        assert [h.id for h in first.hazards] == [h.id for h in second.hazards]
        assert [r.id for r in first.resources] == [r.id for r in second.resources]
        assert [i.id for i in first.infrastructure] == [i.id for i in second.infrastructure]
        assert [rt.id for rt in first.routes] == [rt.id for rt in second.routes]

    def test_every_entity_is_marked_simulated(self) -> None:
        scenario = build_demo_scenario()
        assert scenario.disaster.is_simulated is True
        assert all(o.is_simulated for o in scenario.observations)
        assert all(a.is_simulated for a in scenario.affected_areas)
        assert all(h.is_simulated for h in scenario.hazards)
        assert all(r.is_simulated for r in scenario.resources)

    def test_has_at_least_one_unavailable_resource_and_one_capability_mismatch(self) -> None:
        # "Having equipment is not enough" — see module docstring.
        scenario = build_demo_scenario()
        from app.intelligence.schemas import ResourceAvailability, ResourceCapability

        unavailable = [
            r for r in scenario.resources if r.availability == ResourceAvailability.UNAVAILABLE
        ]
        assert unavailable, "expected at least one resource that exists but is not deployable"

        ground_search_capable = [
            r for r in scenario.resources if ResourceCapability.GROUND_SEARCH in r.capabilities
        ]
        non_capable_available = [
            r
            for r in scenario.resources
            if ResourceCapability.GROUND_SEARCH not in r.capabilities
            and r.availability == ResourceAvailability.AVAILABLE
        ]
        assert ground_search_capable, "expected at least one GROUND_SEARCH-capable resource"
        assert non_capable_available, (
            "expected at least one available resource lacking GROUND_SEARCH"
        )

    def test_never_uses_a_real_world_location(self) -> None:
        # The same fictional-open-ocean convention as the frontend demo fixtures.
        scenario = build_demo_scenario()
        assert scenario.disaster.location is not None
        lon, lat = scenario.disaster.location.coordinates  # type: ignore[union-attr]
        assert (lon, lat) == (1.5, 1.5)

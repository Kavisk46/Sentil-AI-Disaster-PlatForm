"""Schema validation for the damage-intelligence contracts."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.ml.schemas import BuildingDamage, DamageAnalysis, DamageClass, DamageSummary, ModelStatus
from app.schemas.analysis import AnalysisStatus


def test_damage_class_accepts_known_values() -> None:
    assert DamageClass("no_damage") == DamageClass.NO_DAMAGE
    assert DamageClass("destroyed") == DamageClass.DESTROYED


def test_damage_class_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        DamageClass("catastrophic")  # not one of our normalized classes


def test_building_damage_accepts_valid_confidence() -> None:
    building = BuildingDamage(
        building_id="building_0", damage_class=DamageClass.MINOR, confidence=0.5
    )
    assert building.confidence == 0.5


@pytest.mark.parametrize("confidence", [-0.01, 1.01, 2.0, -5.0])
def test_building_damage_rejects_out_of_range_confidence(confidence: float) -> None:
    with pytest.raises(ValidationError):
        BuildingDamage(
            building_id="building_0", damage_class=DamageClass.MINOR, confidence=confidence
        )


def test_building_damage_rejects_invalid_damage_class() -> None:
    with pytest.raises(ValidationError):
        BuildingDamage.model_validate(
            {"building_id": "building_0", "damage_class": "totally-destroyed", "confidence": 0.9}
        )


def test_damage_summary_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError):
        DamageSummary(total_buildings=-1, damaged_buildings=0, severely_damaged=0, destroyed=0)


def test_damage_analysis_defaults_have_no_fabricated_results() -> None:
    analysis = DamageAnalysis(analysis_id=uuid4(), status=AnalysisStatus.UPLOADED)

    assert analysis.summary is None
    assert analysis.buildings == []


def test_damage_analysis_accepts_completed_results() -> None:
    building = BuildingDamage(
        building_id="building_0", damage_class=DamageClass.DESTROYED, confidence=0.9
    )
    summary = DamageSummary(total_buildings=1, damaged_buildings=1, severely_damaged=1, destroyed=1)

    analysis = DamageAnalysis(
        analysis_id=uuid4(),
        status=AnalysisStatus.COMPLETED,
        summary=summary,
        buildings=[building],
    )

    assert analysis.summary == summary
    assert analysis.buildings == [building]


def test_model_status_is_explicit_about_unloaded_state() -> None:
    status = ModelStatus(
        model_loaded=False,
        model_name="sentinelai-damage-classifier",
        model_version="unconfigured",
        device="cpu",
    )

    assert status.model_loaded is False

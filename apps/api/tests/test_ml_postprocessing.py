"""Postprocessing contract: raw detections -> BuildingDamage / DamageSummary
/ DamageAnalysis.

`RawDetection` instances here are synthetic test fixtures standing in for
what a real model would eventually emit — never served by any endpoint.
"""

from uuid import uuid4

from app.ml.model import RawDetection
from app.ml.postprocessing import build_analysis, summarize_buildings
from app.ml.schemas import BuildingDamage, DamageClass
from app.schemas.analysis import AnalysisStatus


def test_summarize_buildings_counts_by_severity() -> None:
    buildings = [
        BuildingDamage(building_id="b0", damage_class=DamageClass.NO_DAMAGE, confidence=0.9),
        BuildingDamage(building_id="b1", damage_class=DamageClass.MINOR, confidence=0.8),
        BuildingDamage(building_id="b2", damage_class=DamageClass.MAJOR, confidence=0.7),
        BuildingDamage(building_id="b3", damage_class=DamageClass.DESTROYED, confidence=0.95),
        BuildingDamage(building_id="b4", damage_class=DamageClass.DESTROYED, confidence=0.6),
    ]

    summary = summarize_buildings(buildings)

    assert summary.total_buildings == 5
    assert summary.damaged_buildings == 4  # everything except no_damage
    assert summary.severely_damaged == 3  # 1 major + 2 destroyed
    assert summary.destroyed == 2


def test_summarize_buildings_handles_empty_input() -> None:
    summary = summarize_buildings([])

    assert summary.total_buildings == 0
    assert summary.damaged_buildings == 0
    assert summary.severely_damaged == 0
    assert summary.destroyed == 0


def test_build_analysis_assigns_sequential_building_ids() -> None:
    analysis_id = uuid4()
    detections = [
        RawDetection(damage_class=DamageClass.NO_DAMAGE, confidence=0.99),
        RawDetection(damage_class=DamageClass.MAJOR, confidence=0.77),
    ]

    analysis = build_analysis(analysis_id, AnalysisStatus.COMPLETED, detections)

    assert analysis.analysis_id == analysis_id
    assert analysis.status == AnalysisStatus.COMPLETED
    assert [b.building_id for b in analysis.buildings] == ["building_0", "building_1"]
    assert analysis.buildings[1].damage_class == DamageClass.MAJOR


def test_build_analysis_summary_matches_buildings() -> None:
    detections = [
        RawDetection(damage_class=DamageClass.DESTROYED, confidence=0.9),
        RawDetection(damage_class=DamageClass.DESTROYED, confidence=0.85),
    ]

    analysis = build_analysis(uuid4(), AnalysisStatus.COMPLETED, detections)

    assert analysis.summary is not None
    assert analysis.summary.total_buildings == 2
    assert analysis.summary.destroyed == 2


def test_build_analysis_with_no_detections_yields_zeroed_summary() -> None:
    analysis = build_analysis(uuid4(), AnalysisStatus.COMPLETED, [])

    assert analysis.buildings == []
    assert analysis.summary is not None
    assert analysis.summary.total_buildings == 0

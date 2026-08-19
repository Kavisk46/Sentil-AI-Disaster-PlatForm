import pytest

from research.experiments.hazards.evaluation import (
    HazardEvidenceLevel,
    HazardScenario,
    NullHazardAssessor,
    evaluate,
)
from research.experiments.hazards.fixtures import REQUIRED_SCENARIOS


def test_required_scenarios_cover_all_four_evidence_categories() -> None:
    levels = {scenario.evidence_level for scenario in REQUIRED_SCENARIOS}
    assert levels == set(HazardEvidenceLevel)


def test_null_hazard_assessor_always_reports_unavailable() -> None:
    assessor = NullHazardAssessor()
    for level in HazardEvidenceLevel:
        result = assessor.assess(level)
        assert result.available is False
        assert result.reason is not None
        assert result.hazard_type is None


def test_evaluate_against_the_null_assessor_reports_full_coverage_and_correctness() -> None:
    report = evaluate(NullHazardAssessor(), REQUIRED_SCENARIOS)

    assert report.scenarios_run == 4
    assert report.coverage == 1.0
    assert report.scenario_correctness == 1.0
    assert report.scenarios_correct == 4
    assert 0.0 <= report.mean_input_completeness <= 1.0


def test_evaluate_reports_partial_coverage_for_a_subset_of_evidence_levels() -> None:
    subset = [
        scenario
        for scenario in REQUIRED_SCENARIOS
        if scenario.evidence_level is HazardEvidenceLevel.HIGH_RISK
    ]

    report = evaluate(NullHazardAssessor(), subset)

    assert report.coverage == pytest.approx(0.25)  # 1 of 4 required categories


def test_evaluate_reports_incorrectness_when_expectation_mismatches_reality() -> None:
    """A scenario that (incorrectly) expects the null assessor to find
    something available should reduce scenario_correctness — proving the
    report isn't trivially always 100%."""
    optimistic_scenario = HazardScenario(
        scenario_id="wrongly_optimistic",
        evidence_level=HazardEvidenceLevel.HIGH_RISK,
        input_completeness=1.0,
        expected_available=True,
    )

    report = evaluate(NullHazardAssessor(), [optimistic_scenario])

    assert report.scenario_correctness == 0.0


def test_evaluate_requires_at_least_one_scenario() -> None:
    with pytest.raises(ValueError, match="at least one scenario"):
        evaluate(NullHazardAssessor(), [])

"""The hazard-evaluation harness itself — see the package docstring
(`research/experiments/hazards/__init__.py`) for the scientific-integrity
framing this module depends on: it evaluates harness readiness and the
`NullHazardAssessor`'s honesty, never real forecasting accuracy.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class HazardEvidenceLevel(StrEnum):
    HIGH_RISK = "high_risk_evidence"
    LOW_RISK = "low_risk_evidence"
    MISSING_DATA = "missing_data"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True, slots=True)
class HazardAssessmentResult:
    """What a hazard assessor reports for one evidence level.
    `available=False` means "no forecast is being made" — the only value
    `NullHazardAssessor` ever returns."""

    available: bool
    reason: str | None = None
    hazard_type: str | None = None
    """Never set by any assessor that exists in this codebase today — no
    hazard subsystem infers a hazard type."""


class HazardAssessor(Protocol):
    """The interface a FUTURE hazard subsystem would need to implement
    for this evaluation harness to assess it — see the package docstring
    for why no such subsystem exists yet."""

    def assess(self, evidence_level: HazardEvidenceLevel) -> HazardAssessmentResult: ...


class NullHazardAssessor:
    """SentinelAI's actual, current hazard-assessment behavior: always
    unavailable, regardless of evidence level. Not a mock standing in for
    a real system — this literally *is* the real system's behavior
    today, used so the harness has something genuine (not
    mocked-as-if-real) to run against."""

    def assess(self, evidence_level: HazardEvidenceLevel) -> HazardAssessmentResult:
        return HazardAssessmentResult(
            available=False,
            reason=(
                "No hazard-prediction subsystem is implemented in SentinelAI "
                "(see research/experiments/hazards/__init__.py)."
            ),
        )


@dataclass(frozen=True, slots=True)
class HazardScenario:
    scenario_id: str
    evidence_level: HazardEvidenceLevel
    input_completeness: float
    """`0.0`-`1.0` — the fraction of expected evidence fields actually
    present in this scenario's (hypothetical) input."""
    expected_available: bool
    """What a CORRECT assessor should report for this scenario. For
    `NullHazardAssessor` this is always `False` — see the package
    docstring. A future real assessor might legitimately report `True`
    for `HIGH_RISK`/`LOW_RISK` evidence; this field lets the harness
    express that expectation without assuming it."""


@dataclass(frozen=True, slots=True)
class HazardEvaluationReport:
    scenarios_run: int
    scenarios_correct: int
    coverage: float
    """Fraction of the 4 required `HazardEvidenceLevel` categories
    exercised by the given scenarios — a property of the fixture set, not
    of any predictive capability."""
    scenario_correctness: float
    """Fraction of scenarios whose assessor result matched
    `expected_available` — for `NullHazardAssessor` this measures whether
    it consistently and honestly reports unavailability, not forecasting
    accuracy."""
    mean_input_completeness: float


_REQUIRED_EVIDENCE_LEVELS = frozenset(HazardEvidenceLevel)


def evaluate(
    assessor: HazardAssessor, scenarios: Sequence[HazardScenario]
) -> HazardEvaluationReport:
    if not scenarios:
        raise ValueError("evaluate() requires at least one scenario.")

    covered_levels = {scenario.evidence_level for scenario in scenarios}
    coverage = len(covered_levels & _REQUIRED_EVIDENCE_LEVELS) / len(_REQUIRED_EVIDENCE_LEVELS)

    correct = 0
    for scenario in scenarios:
        result = assessor.assess(scenario.evidence_level)
        if result.available == scenario.expected_available:
            correct += 1

    return HazardEvaluationReport(
        scenarios_run=len(scenarios),
        scenarios_correct=correct,
        coverage=coverage,
        scenario_correctness=correct / len(scenarios),
        mean_input_completeness=sum(s.input_completeness for s in scenarios) / len(scenarios),
    )

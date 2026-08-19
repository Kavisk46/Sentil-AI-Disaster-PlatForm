"""The four required hazard-evaluation scenario categories (high-risk
evidence, low-risk evidence, missing data, insufficient-data behavior)."""

from research.experiments.hazards.evaluation import HazardEvidenceLevel, HazardScenario

REQUIRED_SCENARIOS: list[HazardScenario] = [
    HazardScenario(
        scenario_id="high_risk_evidence_v1",
        evidence_level=HazardEvidenceLevel.HIGH_RISK,
        input_completeness=1.0,
        expected_available=False,
    ),
    HazardScenario(
        scenario_id="low_risk_evidence_v1",
        evidence_level=HazardEvidenceLevel.LOW_RISK,
        input_completeness=1.0,
        expected_available=False,
    ),
    HazardScenario(
        scenario_id="missing_data_v1",
        evidence_level=HazardEvidenceLevel.MISSING_DATA,
        input_completeness=0.0,
        expected_available=False,
    ),
    HazardScenario(
        scenario_id="insufficient_data_v1",
        evidence_level=HazardEvidenceLevel.INSUFFICIENT_DATA,
        input_completeness=0.3,
        expected_available=False,
    ),
]
"""`expected_available=False` for every scenario: the only assessor that
exists (`NullHazardAssessor`) has no forecasting capability under any
evidence level — see `research/experiments/hazards/__init__.py`. A
future real hazard subsystem would need its own, different fixture set
reflecting what it actually claims to detect."""

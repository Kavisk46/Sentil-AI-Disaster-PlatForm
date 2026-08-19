import math

import pytest
from pydantic import ValidationError

from research.core.reproducibility import build_reproducibility_metadata
from research.core.schemas import ExperimentResult, ReproducibilityMetadata


def _reproducibility() -> ReproducibilityMetadata:
    return build_reproducibility_metadata(
        scenario_id="s1",
        dataset_version="research-fixture-v1",
        model_version="n/a",
        routing_configuration={},
        risk_configuration={},
    )


def test_valid_experiment_result_round_trips() -> None:
    reproducibility = _reproducibility()
    result = ExperimentResult(
        experiment_id=reproducibility.experiment_id,
        scenario_id="s1",
        configuration="risk_aware",
        distance_km=4.8,
        route_risk=0.31,
        risk_reduction_percent=61.7,
        distance_overhead_percent=14.3,
        runtime_ms=1.23,
        reproducibility=reproducibility,
    )
    restored = ExperimentResult.model_validate_json(result.model_dump_json())
    assert restored == result


def test_experiment_result_allows_none_relative_metrics() -> None:
    result = ExperimentResult(
        experiment_id="x",
        scenario_id="s1",
        configuration="shortest_path",
        distance_km=1.0,
        route_risk=0.0,
        risk_reduction_percent=None,
        distance_overhead_percent=None,
        runtime_ms=0.5,
        reproducibility=_reproducibility(),
    )
    assert result.risk_reduction_percent is None
    assert result.distance_overhead_percent is None


@pytest.mark.parametrize(
    "field_name,bad_value",
    [
        ("distance_km", -1.0),
        ("route_risk", -0.01),
        ("runtime_ms", -5.0),
        ("distance_km", math.nan),
        ("distance_km", math.inf),
    ],
)
def test_experiment_result_rejects_malformed_values(field_name: str, bad_value: float) -> None:
    data: dict[str, object] = {
        "experiment_id": "x",
        "scenario_id": "s1",
        "configuration": "shortest_path",
        "distance_km": 1.0,
        "route_risk": 0.1,
        "runtime_ms": 1.0,
        "reproducibility": _reproducibility(),
    }
    data[field_name] = bad_value
    with pytest.raises(ValidationError):
        ExperimentResult.model_validate(data)


def test_experiment_result_rejects_non_finite_relative_metrics() -> None:
    with pytest.raises(ValidationError):
        ExperimentResult(
            experiment_id="x",
            scenario_id="s1",
            configuration="shortest_path",
            distance_km=1.0,
            route_risk=0.1,
            risk_reduction_percent=math.nan,
            runtime_ms=1.0,
            reproducibility=_reproducibility(),
        )


def test_experiment_result_rejects_missing_required_field() -> None:
    with pytest.raises(ValidationError):
        ExperimentResult.model_validate(
            {
                "experiment_id": "x",
                "scenario_id": "s1",
                # "configuration" missing
                "distance_km": 1.0,
                "route_risk": 0.1,
                "runtime_ms": 1.0,
                "reproducibility": _reproducibility().model_dump(mode="json"),
            }
        )

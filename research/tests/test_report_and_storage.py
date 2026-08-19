import csv
import io
import json
from pathlib import Path

from research.core.report import to_csv, to_json, to_markdown
from research.core.reproducibility import build_reproducibility_metadata
from research.core.result_store import (
    load_raw_result,
    load_raw_results,
    write_raw_result,
    write_raw_results,
)
from research.core.schemas import ExperimentResult


def _result(configuration: str, distance_km: float, route_risk: float) -> ExperimentResult:
    reproducibility = build_reproducibility_metadata(
        scenario_id="diamond_detour_v1",
        dataset_version="research-fixture-v1",
        model_version="n/a",
        routing_configuration={},
        risk_configuration={},
    )
    return ExperimentResult(
        experiment_id=reproducibility.experiment_id,
        scenario_id="diamond_detour_v1",
        configuration=configuration,
        distance_km=distance_km,
        route_risk=route_risk,
        risk_reduction_percent=61.7 if configuration != "shortest_path" else 0.0,
        distance_overhead_percent=14.3 if configuration != "shortest_path" else 0.0,
        runtime_ms=0.5,
        reproducibility=reproducibility,
    )


def test_to_csv_contains_every_result_row_with_real_values() -> None:
    results = [_result("shortest_path", 4.2, 0.81), _result("risk_aware", 4.8, 0.31)]

    csv_text = to_csv(results)
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert len(rows) == 2
    assert rows[0]["configuration"] == "shortest_path"
    assert float(rows[0]["distance_km"]) == 4.2
    assert rows[1]["configuration"] == "risk_aware"
    assert float(rows[1]["route_risk"]) == 0.31


def test_to_json_round_trips_through_experiment_result() -> None:
    results = [_result("shortest_path", 4.2, 0.81)]

    json_text = to_json(results)
    data = json.loads(json_text)

    assert len(data) == 1
    assert data[0]["configuration"] == "shortest_path"
    restored = ExperimentResult.model_validate(data[0])
    assert restored.distance_km == 4.2


def test_to_markdown_contains_a_row_per_result_and_the_title() -> None:
    results = [_result("shortest_path", 4.2, 0.81), _result("risk_aware", 4.8, 0.31)]

    markdown = to_markdown(results, title="Diamond Detour Scenario")

    assert "# Diamond Detour Scenario" in markdown
    assert "shortest_path" in markdown
    assert "risk_aware" in markdown
    assert "4.200" in markdown
    assert "0.310" in markdown


def test_write_and_load_raw_result_round_trips(tmp_path: Path) -> None:
    result = _result("risk_aware", 4.8, 0.31)

    path = write_raw_result(result, directory=tmp_path)
    loaded = load_raw_result(path)

    assert path.name == f"{result.experiment_id}.json"
    assert loaded == result


def test_write_and_load_raw_results_batch(tmp_path: Path) -> None:
    results = [_result("shortest_path", 4.2, 0.81), _result("risk_aware", 4.8, 0.31)]

    paths = write_raw_results(results, directory=tmp_path)
    loaded = load_raw_results(tmp_path)

    assert len(paths) == 2
    assert {result.configuration for result in loaded} == {"shortest_path", "risk_aware"}


def test_load_raw_results_from_a_nonexistent_directory_returns_empty() -> None:
    assert load_raw_results(Path("/does/not/exist/at/all")) == []

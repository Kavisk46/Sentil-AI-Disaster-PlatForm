"""Structured result storage — one JSON file per `ExperimentResult` under
`research/results/raw/`, matching this milestone's requested layout.
Never commits large datasets or model weights (see
`research/results/README.md`); this module only ever writes small,
generated JSON result records.
"""

from collections.abc import Sequence
from pathlib import Path

from research.core.schemas import ExperimentResult

_RESEARCH_ROOT = Path(__file__).resolve().parent.parent
RAW_RESULTS_DIR = _RESEARCH_ROOT / "results" / "raw"
PROCESSED_RESULTS_DIR = _RESEARCH_ROOT / "results" / "processed"


def write_raw_result(result: ExperimentResult, directory: Path = RAW_RESULTS_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{result.experiment_id}.json"
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path


def write_raw_results(
    results: Sequence[ExperimentResult], directory: Path = RAW_RESULTS_DIR
) -> list[Path]:
    return [write_raw_result(result, directory) for result in results]


def load_raw_result(path: Path) -> ExperimentResult:
    return ExperimentResult.model_validate_json(path.read_text(encoding="utf-8"))


def load_raw_results(directory: Path = RAW_RESULTS_DIR) -> list[ExperimentResult]:
    if not directory.exists():
        return []
    return [load_raw_result(path) for path in sorted(directory.glob("*.json"))]

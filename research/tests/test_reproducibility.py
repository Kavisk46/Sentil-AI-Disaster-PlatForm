import platform

import pytest

from research.core.reproducibility import (
    build_reproducibility_metadata,
    capture_hardware_info,
    capture_software_versions,
    new_experiment_id,
)
from research.core.schemas import HardwareInfo


def test_new_experiment_id_is_a_real_uuid_and_unique() -> None:
    first, second = new_experiment_id(), new_experiment_id()
    assert first != second
    assert len(first) == 36  # UUID4 string form


def test_hardware_info_never_captures_a_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    """`platform.node()` returns the machine's hostname — sensitive
    information this milestone must never record. Monkeypatching it to
    raise proves `capture_hardware_info()` never calls it."""

    def _forbidden() -> str:
        raise AssertionError("capture_hardware_info() must never call platform.node()")

    monkeypatch.setattr(platform, "node", _forbidden)

    info = capture_hardware_info()

    assert isinstance(info, HardwareInfo)
    assert set(type(info).model_fields.keys()) == {
        "platform", "platform_release", "machine", "cpu_count"
    }


def test_capture_software_versions_reports_real_python_version() -> None:
    versions = capture_software_versions()
    assert versions.python == platform.python_version()


def test_build_reproducibility_metadata_assembles_every_required_field() -> None:
    metadata = build_reproducibility_metadata(
        scenario_id="diamond_detour_v1",
        dataset_version="research-fixture-v1",
        model_version="n/a (synthetic fixture)",
        routing_configuration={"use_astar_heuristic": False},
        risk_configuration={"cost_penalty_scale": 4.0},
        random_seed=42,
    )

    assert metadata.scenario_id == "diamond_detour_v1"
    assert metadata.dataset_version == "research-fixture-v1"
    assert metadata.random_seed == 42
    assert metadata.routing_configuration == {"use_astar_heuristic": False}
    assert metadata.risk_configuration == {"cost_penalty_scale": 4.0}
    assert metadata.hardware.cpu_count is None or metadata.hardware.cpu_count > 0
    assert metadata.software.python


def test_build_reproducibility_metadata_generates_a_fresh_id_by_default() -> None:
    first = build_reproducibility_metadata(
        scenario_id="s", dataset_version="d", model_version="m",
        routing_configuration={}, risk_configuration={},
    )
    second = build_reproducibility_metadata(
        scenario_id="s", dataset_version="d", model_version="m",
        routing_configuration={}, risk_configuration={},
    )
    assert first.experiment_id != second.experiment_id

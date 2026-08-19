"""Captures `ReproducibilityMetadata` from the real running environment —
never a hand-entered or hardcoded value. Deliberately excludes anything
identifying (hostname, username, IP/MAC, absolute file paths) — see
`research.core.schemas.HardwareInfo` for exactly what's captured instead.
"""

import os
import platform
import uuid
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version
from typing import Any

from research.core.schemas import HardwareInfo, ReproducibilityMetadata, SoftwareVersions

_TRACKED_PACKAGES = ("fastapi", "pydantic", "torch")
_API_PACKAGE = "sentinelai-api"


def new_experiment_id() -> str:
    return str(uuid.uuid4())


def capture_hardware_info() -> HardwareInfo:
    return HardwareInfo(
        platform=platform.system(),
        platform_release=platform.release(),
        machine=platform.machine(),
        cpu_count=os.cpu_count(),
    )


def capture_software_versions() -> SoftwareVersions:
    key_dependencies: dict[str, str] = {}
    for name in _TRACKED_PACKAGES:
        try:
            key_dependencies[name] = _package_version(name)
        except PackageNotFoundError:
            continue

    sentinelai_api_version: str | None
    try:
        sentinelai_api_version = _package_version(_API_PACKAGE)
    except PackageNotFoundError:
        sentinelai_api_version = None

    return SoftwareVersions(
        python=platform.python_version(),
        sentinelai_api=sentinelai_api_version,
        key_dependencies=key_dependencies,
    )


def build_reproducibility_metadata(
    *,
    scenario_id: str,
    dataset_version: str,
    model_version: str,
    routing_configuration: dict[str, Any],
    risk_configuration: dict[str, Any],
    random_seed: int | None = None,
    experiment_id: str | None = None,
) -> ReproducibilityMetadata:
    return ReproducibilityMetadata(
        experiment_id=experiment_id or new_experiment_id(),
        timestamp=datetime.now(UTC),
        dataset_version=dataset_version,
        scenario_id=scenario_id,
        model_version=model_version,
        routing_configuration=routing_configuration,
        risk_configuration=risk_configuration,
        random_seed=random_seed,
        hardware=capture_hardware_info(),
        software=capture_software_versions(),
    )

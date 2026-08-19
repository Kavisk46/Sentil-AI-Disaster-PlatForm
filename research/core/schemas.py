"""The research-result schema: `ExperimentResult` and the
`ReproducibilityMetadata` every result carries.

Pydantic validation is what satisfies this milestone's "malformed
experiment results" requirement — a negative distance, a non-finite risk
score, or a missing required field is rejected at construction time, the
same discipline `apps/api/app` uses throughout (see e.g.
`app.roads.schemas.RoadEdge`'s own field validators).
"""

import math
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class HardwareInfo(BaseModel):
    """Coarse, non-identifying hardware facts only — deliberately never
    hostname (`platform.node()`), username, IP, or MAC address. See
    `research.core.reproducibility.capture_hardware_info`.
    """

    platform: str = Field(description="e.g. 'Windows', 'Linux', 'Darwin' — platform.system().")
    platform_release: str
    machine: str = Field(description="e.g. 'AMD64', 'x86_64' — platform.machine().")
    cpu_count: int | None


class SoftwareVersions(BaseModel):
    """Installed package versions relevant to reproducing a result —
    never a full dependency tree, just the packages that could plausibly
    change a routing/risk/incident computation's output."""

    python: str
    sentinelai_api: str | None = Field(
        default=None, description="Version of the installed 'sentinelai-api' package, if found."
    )
    key_dependencies: dict[str, str] = Field(default_factory=dict)


class ReproducibilityMetadata(BaseModel):
    """Everything Milestone 10's "Reproducibility" section requires,
    minus anything sensitive (no file paths, no usernames, no network
    identifiers). Attached to every `ExperimentResult`."""

    experiment_id: str
    timestamp: datetime
    dataset_version: str = Field(
        description="Identifies which fixture/dataset produced this result — never a real, "
        "committed large dataset (see research/results/README.md)."
    )
    scenario_id: str
    model_version: str = Field(
        description="The ML model version involved, or an explicit 'n/a' string when none is "
        "(e.g. a synthetic routing fixture involves no ML model at all) — never fabricated."
    )
    routing_configuration: dict[str, Any]
    risk_configuration: dict[str, Any]
    random_seed: int | None = None
    hardware: HardwareInfo
    software: SoftwareVersions


class ExperimentResult(BaseModel):
    """One configuration's measured outcome for one scenario — the
    schema every routing-evaluation record in this milestone conforms to.
    Matches the Milestone 10 spec's own JSON example field-for-field
    (`distance_km`, `route_risk`, `risk_reduction_percent`,
    `distance_overhead_percent`, `runtime_ms`), plus `found` (whether a
    route existed at all) and full `reproducibility` metadata.
    """

    experiment_id: str
    scenario_id: str
    configuration: str = Field(
        description="A configuration name, e.g. 'shortest_path' / 'risk_aware' / "
        "'ablation_b_damage_only' — see research.experiments.routing.ablation."
    )
    distance_km: float
    route_risk: float
    risk_reduction_percent: float | None = Field(
        default=None,
        description="(baseline_risk - method_risk) / baseline_risk * 100. `None` when the "
        "baseline route had zero risk — reduction relative to zero is undefined, not 0%.",
    )
    distance_overhead_percent: float | None = Field(
        default=None,
        description="(method_distance - baseline_distance) / baseline_distance * 100. `None` "
        "when no meaningful baseline distance exists (e.g. the baseline route wasn't found).",
    )
    runtime_ms: float
    found: bool = Field(
        default=True, description="Whether this configuration found a route at all."
    )
    reproducibility: ReproducibilityMetadata

    @field_validator("distance_km", "route_risk", "runtime_ms")
    @classmethod
    def _finite_and_non_negative(cls, value: float, info: Any) -> float:
        if not math.isfinite(value) or value < 0:
            raise ValueError(
                f"{info.field_name} must be a finite, non-negative number; got {value!r}."
            )
        return value

    @field_validator("risk_reduction_percent", "distance_overhead_percent")
    @classmethod
    def _finite_if_present(cls, value: float | None, info: Any) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError(f"{info.field_name} must be finite if given; got {value!r}.")
        return value

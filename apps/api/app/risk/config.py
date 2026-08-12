"""Centralizes every tunable constant the road-risk formula uses.

`RoadRiskConfig` is a plain, immutable, structured view over the
`ROAD_RISK_*` fields on `Settings` (`app/core/config.py`) — sourced from
Settings so a deployment can retune the model via environment variables,
but assembled once into a typed object here so `app/risk/formula.py` and
`app/risk/analyzer.py` never read `Settings` (or a raw dict) directly.
Nothing in `app/risk/` hardcodes a weight, radius, or threshold inline —
every constant traces back to exactly one place.
"""

from dataclasses import dataclass

from app.core.config import Settings
from app.ml.schemas import DamageClass


@dataclass(frozen=True, slots=True)
class RoadRiskConfig:
    """See `app/core/config.py`'s `ROAD_RISK_*` fields for what each value
    means and its default/rationale. Deliberately no defaults of its own
    (every field required) so the numeric constants live in exactly one
    place (`Settings`) — construct via `from_settings()` for production
    values, or pass every field explicitly (e.g. in a test exercising one
    parameter in isolation) rather than relying on a second, possibly
    drifting set of defaults here.

    Validated once at construction so a misconfigured threshold ordering
    fails loudly instead of silently misclassifying every edge.
    """

    severity_weights: dict[DamageClass, float]
    search_radius_meters: float
    distance_decay_rate: float
    aggregation_cap: float
    risk_level_low_max: float
    risk_level_moderate_max: float
    risk_level_high_max: float
    cost_penalty_scale: float

    def __post_init__(self) -> None:
        thresholds_ordered = (
            0.0 <= self.risk_level_low_max < self.risk_level_moderate_max < self.risk_level_high_max
        )
        if not thresholds_ordered:
            raise ValueError(
                "Risk level thresholds must satisfy "
                "0 <= low_max < moderate_max < high_max; got "
                f"({self.risk_level_low_max}, {self.risk_level_moderate_max}, "
                f"{self.risk_level_high_max})."
            )
        if self.aggregation_cap <= 0:
            raise ValueError(f"aggregation_cap must be positive; got {self.aggregation_cap!r}.")
        if self.search_radius_meters <= 0:
            raise ValueError(
                f"search_radius_meters must be positive; got {self.search_radius_meters!r}."
            )

    @classmethod
    def from_settings(cls, settings: Settings) -> "RoadRiskConfig":
        return cls(
            severity_weights={
                DamageClass.NO_DAMAGE: settings.ROAD_RISK_SEVERITY_WEIGHT_NO_DAMAGE,
                DamageClass.MINOR: settings.ROAD_RISK_SEVERITY_WEIGHT_MINOR,
                DamageClass.MAJOR: settings.ROAD_RISK_SEVERITY_WEIGHT_MAJOR,
                DamageClass.DESTROYED: settings.ROAD_RISK_SEVERITY_WEIGHT_DESTROYED,
            },
            search_radius_meters=settings.ROAD_RISK_SEARCH_RADIUS_METERS,
            distance_decay_rate=settings.ROAD_RISK_DISTANCE_DECAY_RATE,
            aggregation_cap=settings.ROAD_RISK_AGGREGATION_CAP,
            risk_level_low_max=settings.ROAD_RISK_LEVEL_LOW_MAX,
            risk_level_moderate_max=settings.ROAD_RISK_LEVEL_MODERATE_MAX,
            risk_level_high_max=settings.ROAD_RISK_LEVEL_HIGH_MAX,
            cost_penalty_scale=settings.ROAD_RISK_COST_PENALTY_SCALE,
        )

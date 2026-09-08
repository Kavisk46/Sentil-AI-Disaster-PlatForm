"""Centralizes every tunable constant the search-priority scorer and
capability matcher use.

Mirrors `app.risk.config.RoadRiskConfig`: a plain, immutable, structured
view over `INTELLIGENCE_*`/`SEARCH_PRIORITY_*` fields on `Settings`
(`app/core/config.py`), sourced from Settings so a deployment can retune
these via environment variables, but assembled once into a typed object
here so `search_priority.py`/`capability_matching.py` never read
`Settings` directly. Nothing in `app/intelligence/` hardcodes a weight or
threshold inline — every constant traces back to exactly one place.
"""

from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class SearchPriorityConfig:
    """Weights and thresholds for
    `app.intelligence.search_priority.score_search_zone()`.

    Weights must sum to 1.0 over the *full* factor set — when a factor is
    unavailable for a given `AffectedArea`, the scorer renormalizes over
    only the factors it actually has data for (see `search_priority.py`),
    rather than treating a missing factor as zero (which would silently
    penalize) or fabricating a value for it.
    """

    damage_severity_weight: float
    accessibility_weight: float
    population_exposure_weight: float
    evidence_strength_weight: float
    population_exposure_cap: float
    critical_threshold: float
    high_threshold: float
    moderate_threshold: float

    def __post_init__(self) -> None:
        total = (
            self.damage_severity_weight
            + self.accessibility_weight
            + self.population_exposure_weight
            + self.evidence_strength_weight
        )
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"SearchPriorityConfig weights must sum to 1.0; got {total}.")
        for name, value in (
            ("damage_severity_weight", self.damage_severity_weight),
            ("accessibility_weight", self.accessibility_weight),
            ("population_exposure_weight", self.population_exposure_weight),
            ("evidence_strength_weight", self.evidence_strength_weight),
        ):
            if value < 0:
                raise ValueError(f"{name} must be >= 0; got {value!r}.")
        if self.population_exposure_cap <= 0:
            raise ValueError(
                f"population_exposure_cap must be positive; got {self.population_exposure_cap!r}."
            )
        thresholds_ordered = (
            0.0 <= self.moderate_threshold < self.high_threshold < self.critical_threshold <= 1.0
        )
        if not thresholds_ordered:
            raise ValueError(
                "Priority thresholds must satisfy "
                "0 <= moderate < high < critical <= 1; got "
                f"({self.moderate_threshold}, {self.high_threshold}, {self.critical_threshold})."
            )

    @classmethod
    def from_settings(cls, settings: Settings) -> "SearchPriorityConfig":
        return cls(
            damage_severity_weight=settings.SEARCH_PRIORITY_DAMAGE_SEVERITY_WEIGHT,
            accessibility_weight=settings.SEARCH_PRIORITY_ACCESSIBILITY_WEIGHT,
            population_exposure_weight=settings.SEARCH_PRIORITY_POPULATION_EXPOSURE_WEIGHT,
            evidence_strength_weight=settings.SEARCH_PRIORITY_EVIDENCE_STRENGTH_WEIGHT,
            population_exposure_cap=settings.SEARCH_PRIORITY_POPULATION_EXPOSURE_CAP,
            critical_threshold=settings.SEARCH_PRIORITY_CRITICAL_THRESHOLD,
            high_threshold=settings.SEARCH_PRIORITY_HIGH_THRESHOLD,
            moderate_threshold=settings.SEARCH_PRIORITY_MODERATE_THRESHOLD,
        )


@dataclass(frozen=True, slots=True)
class CapabilityMatchingConfig:
    """Tunables for `app.intelligence.capability_matching.rank_candidates()`."""

    max_reachable_distance_meters: float

    def __post_init__(self) -> None:
        if self.max_reachable_distance_meters <= 0:
            raise ValueError(
                "max_reachable_distance_meters must be positive; got "
                f"{self.max_reachable_distance_meters!r}."
            )

    @classmethod
    def from_settings(cls, settings: Settings) -> "CapabilityMatchingConfig":
        return cls(
            max_reachable_distance_meters=settings.CAPABILITY_MATCHING_MAX_DISTANCE_METERS,
        )

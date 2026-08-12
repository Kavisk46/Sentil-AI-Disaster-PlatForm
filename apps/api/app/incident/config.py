"""Centralizes every tunable constant `app.incident.severity` uses.

`IncidentConfig` is a plain, immutable, structured view over the
`INCIDENT_*` fields on `Settings` (`app/core/config.py`) — the same
pattern `RoadRiskConfig`/`RoutingConfig` already established. Nothing in
`app/incident/` hardcodes a threshold inline.
"""

from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class IncidentConfig:
    """See `app/core/config.py`'s `INCIDENT_*` fields for what each value
    means. Deliberately no defaults of its own — construct via
    `from_settings()` or pass every field explicitly, same reasoning as
    `RoadRiskConfig`/`RoutingConfig`: one source of truth for the numbers.
    """

    max_listed_structure_ids: int
    severity_destroyed_ratio_critical: float
    severity_severe_ratio_high: float
    severity_severe_ratio_moderate: float
    confidence_high_min: float
    confidence_moderate_min: float

    def __post_init__(self) -> None:
        if self.max_listed_structure_ids < 0:
            raise ValueError(
                f"max_listed_structure_ids must be non-negative; got {self.max_listed_structure_ids!r}."
            )
        severity_ordered = self.severity_severe_ratio_moderate <= self.severity_severe_ratio_high
        if not severity_ordered:
            raise ValueError(
                "severity_severe_ratio_moderate must be <= severity_severe_ratio_high; got "
                f"({self.severity_severe_ratio_moderate}, {self.severity_severe_ratio_high})."
            )
        confidence_ordered = self.confidence_moderate_min <= self.confidence_high_min
        if not confidence_ordered:
            raise ValueError(
                "confidence_moderate_min must be <= confidence_high_min; got "
                f"({self.confidence_moderate_min}, {self.confidence_high_min})."
            )

    @classmethod
    def from_settings(cls, settings: Settings) -> "IncidentConfig":
        return cls(
            max_listed_structure_ids=settings.INCIDENT_MAX_LISTED_STRUCTURE_IDS,
            severity_destroyed_ratio_critical=settings.INCIDENT_SEVERITY_DESTROYED_RATIO_CRITICAL,
            severity_severe_ratio_high=settings.INCIDENT_SEVERITY_SEVERE_RATIO_HIGH,
            severity_severe_ratio_moderate=settings.INCIDENT_SEVERITY_SEVERE_RATIO_MODERATE,
            confidence_high_min=settings.INCIDENT_CONFIDENCE_HIGH_MIN,
            confidence_moderate_min=settings.INCIDENT_CONFIDENCE_MODERATE_MIN,
        )

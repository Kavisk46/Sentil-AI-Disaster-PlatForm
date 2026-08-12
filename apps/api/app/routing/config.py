"""Centralizes every tunable constant the routing engine uses.

`RoutingConfig` is a plain, immutable, structured view over the
`ROUTING_*` fields on `Settings` (`app/core/config.py`), the same pattern
`app.risk.config.RoadRiskConfig` already established — sourced from
Settings so a deployment can retune routing via environment variables,
assembled once into a typed object so nothing in `app/routing/` reads
`Settings` (or a raw dict) directly.
"""

from dataclasses import dataclass

from app.core.config import Settings
from app.routing.accessibility import Traversability


@dataclass(frozen=True, slots=True)
class RoutingConfig:
    """See `app/core/config.py`'s `ROUTING_*` fields for what each value
    means and its default/rationale. Deliberately no defaults of its own
    (every field required) — same reasoning as `RoadRiskConfig`: construct
    via `from_settings()` for production values, or pass every field
    explicitly in a test exercising one parameter in isolation, rather
    than risking a second, possibly drifting set of defaults here.
    """

    restricted_accessibility_penalty: float
    unknown_accessibility_policy: Traversability
    max_snap_distance_meters: float
    use_astar_heuristic: bool

    def __post_init__(self) -> None:
        if self.restricted_accessibility_penalty < 0:
            raise ValueError(
                "restricted_accessibility_penalty must be non-negative; got "
                f"{self.restricted_accessibility_penalty!r}."
            )
        if self.max_snap_distance_meters <= 0:
            raise ValueError(
                f"max_snap_distance_meters must be positive; got {self.max_snap_distance_meters!r}."
            )

    @classmethod
    def from_settings(cls, settings: Settings) -> "RoutingConfig":
        unknown_policy = Traversability(settings.ROUTING_UNKNOWN_ACCESSIBILITY_POLICY)
        return cls(
            restricted_accessibility_penalty=settings.ROUTING_RESTRICTED_ACCESSIBILITY_PENALTY,
            unknown_accessibility_policy=unknown_policy,
            max_snap_distance_meters=settings.ROUTING_MAX_SNAP_DISTANCE_METERS,
            use_astar_heuristic=settings.ROUTING_USE_ASTAR_HEURISTIC,
        )

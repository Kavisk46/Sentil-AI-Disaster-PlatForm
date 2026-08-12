"""Damage-based building priority — deterministic, damage-severity only.

Explicitly labeled **damage-based priority**, not a complete
emergency-response prioritization model. A real triage priority would also
incorporate:

- population (how many people are near/in the building)
- proximity to hospitals, schools, and other critical infrastructure
- road accessibility (can rescue crews actually reach it)
- hazard risk (aftershocks, flooding, fire spread, structural collapse risk)
- prediction uncertainty (a low-confidence "destroyed" call shouldn't
  outrank a high-confidence one)

None of that data exists in this codebase yet, so none of it is used here.
Ordering by damage severity alone (`destroyed > major > minor > no_damage`)
is a deliberately simple, honest first version — not a claim that damage
class alone is sufficient for real rescue prioritization.
"""

from enum import StrEnum

from app.ml.schemas import DamageClass


class DamagePriority(StrEnum):
    """Ordered `LOW < MEDIUM < HIGH < CRITICAL`, driven only by
    `DamageClass` — see the module docstring for what a real triage
    priority would additionally need."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_RANK: dict[DamagePriority, int] = {
    DamagePriority.LOW: 0,
    DamagePriority.MEDIUM: 1,
    DamagePriority.HIGH: 2,
    DamagePriority.CRITICAL: 3,
}

_PRIORITY_BY_DAMAGE_CLASS: dict[DamageClass, DamagePriority] = {
    DamageClass.NO_DAMAGE: DamagePriority.LOW,
    DamageClass.MINOR: DamagePriority.MEDIUM,
    DamageClass.MAJOR: DamagePriority.HIGH,
    DamageClass.DESTROYED: DamagePriority.CRITICAL,
}

_HIGH_PRIORITY = frozenset({DamagePriority.HIGH, DamagePriority.CRITICAL})


def compute_damage_priority(damage_class: DamageClass) -> DamagePriority:
    """Damage-based priority only — see the module docstring."""
    return _PRIORITY_BY_DAMAGE_CLASS[damage_class]


def priority_rank(priority: DamagePriority) -> int:
    """Sortable rank, `CRITICAL` highest — `sorted(..., key=priority_rank)`
    today, `ORDER BY priority_rank DESC` in a future PostGIS query."""
    return _RANK[priority]


def is_high_priority(damage_class: DamageClass) -> bool:
    """`HIGH` or `CRITICAL` — the threshold
    `SpatialRepository.get_high_priority_buildings()` uses."""
    return compute_damage_priority(damage_class) in _HIGH_PRIORITY

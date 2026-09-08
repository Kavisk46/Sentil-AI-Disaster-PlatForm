"""The **deterministic baseline search-priority scorer**.

    priority_score = sum(value_i * weight_i for available factors)
                      / sum(weight_i for available factors)

**This is a deterministic, explainable BASELINE HEURISTIC — not a
validated search-and-rescue triage model.** It has not been calibrated
against any real disaster/rescue outcome data. It exists to give the
architecture (Affected Area -> Search Zone -> Recommendation) a real,
working, honestly-labeled implementation to build on, replace, or compare
against once real outcome data and a learned model exist — see
`docs/research/intelligence-baselines.md`.

A `SearchZone` produced by this module is **never** a claim that a person
is located there. It is a ranked candidate for investigation, with every
contributing factor and every missing factor disclosed.

## Why each factor is in the formula

- **Damage severity** — a more severely damaged structure more plausibly
  has people trapped or unable to self-evacuate. Reuses
  `app.ml.geospatial.priority.compute_damage_priority`/`priority_rank`
  (the existing, damage-only ordinal scale) rather than a second damage
  ranking.
- **Accessibility** — a `BLOCKED`/`RESTRICTED` area is one where affected
  people are *less* able to reach help on their own, raising search
  urgency; `OPEN` areas are more likely already reachable by the affected
  population itself. This is a documented, debatable modeling choice —
  not the only reasonable interpretation of "accessibility matters" — see
  the module's test suite for the exact mapping.
- **Population exposure** — more people potentially present raises the
  expected value of investigating the zone. Only ever used when a real
  population figure is supplied; never estimated (project constraint:
  "Do not invent population estimates").
- **Evidence strength** — a zone assessed with low uncertainty and
  multiple corroborating observations is a more trustworthy candidate
  than one with high uncertainty and a single, weak observation.

## Missing factors are never fabricated

If `AffectedArea.affected_population` is `None`, the population-exposure
factor is **omitted** from the weighted sum entirely, and the remaining
factors' weights are renormalized (divided by the sum of weights actually
used) rather than treating the missing factor as `0` (which would
silently penalize the zone) or `1` (which would silently inflate it).
Every omitted factor is recorded in `SearchZone.missing_factors` and
pushes `SearchZone.uncertainty` one level less confident.
"""

from uuid import UUID, uuid4

from app.intelligence.config import SearchPriorityConfig
from app.intelligence.schemas import (
    AffectedArea,
    SearchPriorityLevel,
    SearchZone,
    SearchZoneFactor,
    Uncertainty,
    UncertaintyLevel,
)
from app.ml.geospatial.priority import compute_damage_priority, priority_rank
from app.roads.schemas import AccessibilityStatus

_MAX_DAMAGE_RANK = 3  # priority_rank(CRITICAL) — see app.ml.geospatial.priority

# Higher = less accessible = more urgent to investigate (see module docstring).
_ACCESSIBILITY_VALUE: dict[AccessibilityStatus, float] = {
    AccessibilityStatus.BLOCKED: 1.0,
    AccessibilityStatus.RESTRICTED: 0.6,
    AccessibilityStatus.OPEN: 0.2,
}

_EVIDENCE_STRENGTH_BASE: dict[UncertaintyLevel, float] = {
    UncertaintyLevel.LOW: 0.9,
    UncertaintyLevel.MODERATE: 0.6,
    UncertaintyLevel.HIGH: 0.3,
    UncertaintyLevel.UNKNOWN: 0.1,
}

_UNCERTAINTY_ESCALATION: dict[UncertaintyLevel, UncertaintyLevel] = {
    UncertaintyLevel.LOW: UncertaintyLevel.MODERATE,
    UncertaintyLevel.MODERATE: UncertaintyLevel.HIGH,
    UncertaintyLevel.HIGH: UncertaintyLevel.HIGH,
    UncertaintyLevel.UNKNOWN: UncertaintyLevel.UNKNOWN,
}


def _damage_severity_factor(area: AffectedArea, config: SearchPriorityConfig) -> SearchZoneFactor:
    priority = compute_damage_priority(area.damage_level)
    value = priority_rank(priority) / _MAX_DAMAGE_RANK
    return SearchZoneFactor(
        name="damage_severity",
        value=value,
        weight=config.damage_severity_weight,
        contribution=value * config.damage_severity_weight,
        description=(
            f"Observed damage level is '{area.damage_level.value}' (priority: {priority.value})."
        ),
    )


def _accessibility_factor(
    area: AffectedArea, config: SearchPriorityConfig
) -> SearchZoneFactor | None:
    """`None` when accessibility is unknown or wasn't assessed — an
    unknown accessibility carries no directional signal, so it is
    dropped from scoring rather than guessed."""
    if area.accessibility is None or area.accessibility == AccessibilityStatus.UNKNOWN:
        return None
    value = _ACCESSIBILITY_VALUE[area.accessibility]
    return SearchZoneFactor(
        name="accessibility",
        value=value,
        weight=config.accessibility_weight,
        contribution=value * config.accessibility_weight,
        description=f"Area accessibility is '{area.accessibility.value}'.",
    )


def _population_exposure_factor(
    area: AffectedArea, config: SearchPriorityConfig
) -> SearchZoneFactor | None:
    """`None` whenever no real population figure exists — never
    estimated (project constraint: "Do not invent population
    estimates")."""
    if area.affected_population is None:
        return None
    value = min(area.affected_population / config.population_exposure_cap, 1.0)
    return SearchZoneFactor(
        name="population_exposure",
        value=value,
        weight=config.population_exposure_weight,
        contribution=value * config.population_exposure_weight,
        description=(
            f"{area.affected_population} affected people reported "
            f"(capped at {config.population_exposure_cap:.0f} for scoring)."
        ),
    )


def _evidence_strength_factor(area: AffectedArea, config: SearchPriorityConfig) -> SearchZoneFactor:
    """Always available: `AffectedArea.uncertainty` is a required field,
    so this factor never needs to be omitted. A small, capped bonus per
    additional corroborating evidence item rewards multiply-observed
    areas without letting evidence volume alone dominate the score."""
    base = _EVIDENCE_STRENGTH_BASE[area.uncertainty.level]
    evidence_count = len(area.evidence)
    bonus = min(0.1 * max(evidence_count - 1, 0), 0.1) if evidence_count > 0 else -0.1
    value = max(0.0, min(1.0, base + bonus))
    return SearchZoneFactor(
        name="evidence_strength",
        value=value,
        weight=config.evidence_strength_weight,
        contribution=value * config.evidence_strength_weight,
        description=(
            f"Assessment uncertainty is '{area.uncertainty.level.value}', backed by "
            f"{evidence_count} evidence item(s)."
        ),
    )


def _classify_priority_level(score: float, config: SearchPriorityConfig) -> SearchPriorityLevel:
    if score >= config.critical_threshold:
        return SearchPriorityLevel.CRITICAL
    if score >= config.high_threshold:
        return SearchPriorityLevel.HIGH
    if score >= config.moderate_threshold:
        return SearchPriorityLevel.MODERATE
    return SearchPriorityLevel.LOW


def _zone_uncertainty(area: AffectedArea, missing_factors: list[str]) -> Uncertainty:
    """Derived from the source `AffectedArea`'s own uncertainty, escalated
    one level for each distinct kind of missing data (capped — see
    `_UNCERTAINTY_ESCALATION`). `confidence` is always `None`: this is a
    heuristic-derived score, not a calibrated probability, so no
    numerical confidence is ever attached to it (project constraint:
    "DO NOT create fake numerical confidence")."""
    level = area.uncertainty.level
    reason = f"Derived from the source area's own uncertainty ({area.uncertainty.reason})."
    if missing_factors:
        level = _UNCERTAINTY_ESCALATION[level]
        reason += (
            f" Escalated because the following factors were not scoreable: "
            f"{', '.join(missing_factors)}."
        )
    return Uncertainty(
        level=level,
        confidence=None,
        reason=reason,
        missing_information=list(missing_factors),
        source_limitations=list(area.uncertainty.source_limitations),
    )


def score_search_zone(
    area: AffectedArea,
    config: SearchPriorityConfig,
    *,
    zone_id: UUID | None = None,
) -> SearchZone:
    """Score one `AffectedArea` into a `SearchZone`. Pure function of
    `area` and `config` — no I/O, fully deterministic, safe to call
    repeatedly with the same result (see `app.services.intelligence_service`,
    which does exactly that rather than caching)."""
    candidate_factors: list[tuple[str, SearchZoneFactor | None]] = [
        ("damage_severity", _damage_severity_factor(area, config)),
        ("accessibility", _accessibility_factor(area, config)),
        ("population_exposure", _population_exposure_factor(area, config)),
        ("evidence_strength", _evidence_strength_factor(area, config)),
    ]

    factors = [factor for _, factor in candidate_factors if factor is not None]
    missing_factors = [name for name, factor in candidate_factors if factor is None]

    total_weight_used = sum(f.weight for f in factors)
    score = sum(f.contribution for f in factors) / total_weight_used

    reasons = [f.description for f in factors]
    if missing_factors:
        reasons.append(
            "The following factor(s) could not be scored due to missing data: "
            f"{', '.join(missing_factors)}."
        )

    return SearchZone(
        id=zone_id or uuid4(),
        geometry=area.geometry,
        geometry_crs=area.geometry_crs,
        priority_score=round(score, 4),
        priority_level=_classify_priority_level(score, config),
        factors=factors,
        missing_factors=missing_factors,
        reasons=reasons,
        supporting_observations=[],
        supporting_evidence=list(area.evidence),
        uncertainty=_zone_uncertainty(area, missing_factors),
        is_simulated=area.is_simulated,
    )


def rank_search_zones(zones: list[SearchZone]) -> list[SearchZone]:
    """Descending by `priority_score` — ties broken by id for a stable,
    deterministic order across repeated calls."""
    return sorted(zones, key=lambda z: (-z.priority_score, str(z.id)))

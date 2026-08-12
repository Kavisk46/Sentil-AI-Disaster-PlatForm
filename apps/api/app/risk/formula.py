"""The **baseline heuristic road-risk model** (Milestone 6B).

    risk contribution = severity_weight(damage_class) x distance_decay(distance) x confidence

**This is a deterministic, explainable BASELINE HEURISTIC — not a
scientifically validated risk model.** It has not been calibrated or
evaluated against any real disaster data; it exists to give the
architecture (Spatial Analysis -> Road Risk -> Risk-aware Road Graph) a
real, working, honestly-labeled implementation to build on, replace, or
compare against once real data and a learned model exist. See
`apps/api/README.md` ("Road risk model") for the full research writeup.

## Why each term is in the formula

- **Damage severity matters** because a road passing next to a destroyed
  building is plausibly more affected (debris, structural collapse onto
  the roadway, downed utility lines) than one passing next to a building
  with only minor damage. `severity_weight()` encodes this as an ordinal
  scale (`no_damage` < `minor` < `major` < `destroyed`), reusing the
  existing `DamageClass` taxonomy — see `app.ml.geospatial.priority` for
  the same ordering already established for building-level priority.
- **Proximity matters** because damage further from a road is less likely
  to affect it — a destroyed building 500m away is not a reason to avoid
  a road, while one 5m away plausibly is. `distance_decay()` is a smooth,
  monotonically decreasing function of distance, not a hard cutoff, so a
  building just past some threshold doesn't suddenly contribute zero.
- **Confidence can affect risk** because a low-confidence detection is
  less trustworthy evidence than a high-confidence one; multiplying by
  `confidence` (already a well-defined `[0, 1]` field on every
  `BuildingDamage` — see `app.ml.schemas`) lets uncertain detections
  contribute proportionally less, without discarding them outright.
"""

import math
from collections.abc import Sequence

from app.ml.schemas import DamageClass
from app.risk.config import RoadRiskConfig
from app.roads.schemas import RiskLevel


def severity_weight(damage_class: DamageClass, config: RoadRiskConfig) -> float:
    """`config.severity_weights[damage_class]` — see
    `app/core/config.py`'s `ROAD_RISK_SEVERITY_WEIGHT_*` for the centrally
    configured values and their rationale."""
    return config.severity_weights[damage_class]


def distance_decay(distance_meters: float, config: RoadRiskConfig) -> float:
    """Exponential decay: `exp(-decay_rate * distance)`.

    Chosen over a linear or step decay because it has no discontinuity (no
    single meter where contribution suddenly jumps) and is governed by one
    interpretable parameter — its half-life,
    `ln(2) / config.distance_decay_rate` meters (with the default
    `0.02`/meter, roughly 35m). Not fit to any real data — an
    unconstrained modeling choice, like every constant in this module.
    """
    return math.exp(-config.distance_decay_rate * distance_meters)


def contribution(
    damage_class: DamageClass, confidence: float, distance_meters: float, config: RoadRiskConfig
) -> float:
    """One damaged building's contribution to a road edge's risk — the
    product `severity_weight x distance_decay x confidence`, each factor
    in `[0, 1]`, so the product is too."""
    return (
        severity_weight(damage_class, config)
        * distance_decay(distance_meters, config)
        * confidence
    )


def aggregate_contributions(contributions: Sequence[float], config: RoadRiskConfig) -> float:
    """Sum every contribution, then cap to `config.aggregation_cap`
    (`0.0`-`1.0` by default).

    A plain sum — not a maximum, and not a probabilistic combination like
    "noisy-OR" — so that *multiple* nearby damaged buildings compound risk
    rather than the single worst one dominating; this is simple, easy to
    explain to a non-technical responder ("three moderately-damaged
    buildings nearby added up"), and monotonic (adding another damaged
    building can only ever raise or hold risk, never lower it). The cap
    prevents unbounded accumulation from many nearby buildings — without
    it, a cluster of ten destroyed buildings could otherwise report a risk
    score of 6 or more, which is meaningless once risk is meant to read as
    "0 = none, 1 = maximal."
    """
    return min(config.aggregation_cap, max(0.0, sum(contributions)))


def classify_risk_level(risk_score: float, config: RoadRiskConfig) -> RiskLevel:
    """`low` / `moderate` / `high` / `critical`, from the centrally
    configured thresholds (`config.risk_level_*_max`). **Engineering
    categories, not validated emergency-management risk classes** — see
    `app.roads.schemas.RiskLevel`.
    """
    if risk_score <= config.risk_level_low_max:
        return RiskLevel.LOW
    if risk_score <= config.risk_level_moderate_max:
        return RiskLevel.MODERATE
    if risk_score <= config.risk_level_high_max:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


def compute_risk_adjusted_cost(
    base_cost: float, risk_score: float | None, config: RoadRiskConfig
) -> float:
    """`base_cost * (1 + cost_penalty_scale * risk_score)`.

    `risk_score is None` (this edge has never been assessed for risk)
    returns `base_cost` unchanged — an edge nobody has evaluated must not
    silently become more expensive than an edge confirmed to have zero
    nearby damage (`risk_score == 0.0`, which correctly *does* leave
    `base_cost` unchanged too, since the penalty term is `0`). Not applied
    to `RoadEdge.accessibility` in any way — an edge's routability
    (`open`/`restricted`/`blocked`/`unknown`) and its cost are deliberately
    independent; see `app.risk` ("Why risk is not blockage"). No routing
    algorithm consumes this yet — see "Do not implement" in
    `apps/api/README.md`.
    """
    if risk_score is None:
        return base_cost
    return base_cost * (1 + config.cost_penalty_scale * risk_score)

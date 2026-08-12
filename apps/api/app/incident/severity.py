"""Deterministic classification of incident severity and confidence.

Kept in its own module, separate from `context_builder.py`, specifically
because this is the boundary the milestone requires never be crossed by
an LLM: `classify_incident_severity()`/`classify_confidence()` are pure
functions of `IncidentContext`'s already-real numbers, and their output
is what `app.incident.briefing_builder` puts into the final
`IncidentBriefing` — an LLM's own opinion of severity or confidence is
never consulted, let alone trusted.

**These are engineering categories, not a validated emergency-management
severity scale** — the same honesty this codebase already applies to
`RiskLevel` (Milestone 6B) and `DamagePriority` (Milestone 5). Every
threshold is centralized in `IncidentConfig`, sourced from `Settings`.
"""

from app.incident.config import IncidentConfig
from app.incident.schemas import (
    AffectedStructuresSummary,
    ConfidenceLevel,
    IncidentContext,
    IncidentSeverity,
)


def classify_incident_severity(context: IncidentContext, config: IncidentConfig) -> IncidentSeverity:
    """`unknown` if damage data isn't available at all — never guessed.
    Otherwise, ordinal thresholds on `destroyed`/`severely_damaged` as a
    fraction of `total_buildings`:

    - `critical` — destroyed ratio >= `severity_destroyed_ratio_critical`
      (default `0.25`).
    - `high` — severely-damaged ratio >= `severity_severe_ratio_high`
      (default `0.5`).
    - `moderate` — severely-damaged ratio >= `severity_severe_ratio_moderate`
      (default `0.2`), or any damage at all.
    - `low` — otherwise (including zero buildings detected).
    """
    if not context.damage.available or context.damage.summary is None:
        return IncidentSeverity.UNKNOWN

    summary = context.damage.summary
    if summary.total_buildings == 0:
        return IncidentSeverity.LOW

    destroyed_ratio = summary.destroyed / summary.total_buildings
    severe_ratio = summary.severely_damaged / summary.total_buildings

    if destroyed_ratio >= config.severity_destroyed_ratio_critical:
        return IncidentSeverity.CRITICAL
    if severe_ratio >= config.severity_severe_ratio_high:
        return IncidentSeverity.HIGH
    if severe_ratio >= config.severity_severe_ratio_moderate or summary.damaged_buildings > 0:
        return IncidentSeverity.MODERATE
    return IncidentSeverity.LOW


def classify_confidence(context: IncidentContext, config: IncidentConfig) -> ConfidenceLevel:
    """`unknown` if there is no detection confidence to summarize at all
    — never a guessed confidence level. Otherwise a threshold on the mean
    `BuildingDamage.confidence` across every detected building (a real
    model output, not an LLM's self-assessment — see `app.incident`,
    "Why the LLM is not the decision-maker")."""
    if not context.damage.available or context.damage.average_confidence is None:
        return ConfidenceLevel.UNKNOWN

    average = context.damage.average_confidence
    if average >= config.confidence_high_min:
        return ConfidenceLevel.HIGH
    if average >= config.confidence_moderate_min:
        return ConfidenceLevel.MODERATE
    return ConfidenceLevel.LOW


def build_affected_structures_summary(context: IncidentContext) -> AffectedStructuresSummary:
    """All-zero if damage data isn't available — never fabricated counts."""
    if not context.damage.available or context.damage.summary is None:
        return AffectedStructuresSummary(
            total=0, damaged=0, severely_damaged=0, destroyed=0, high_priority_count=0
        )
    return AffectedStructuresSummary.from_damage_summary(
        context.damage.summary, len(context.damage.high_priority_structure_ids)
    )

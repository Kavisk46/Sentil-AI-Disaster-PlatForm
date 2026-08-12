"""Assembles the final `IncidentBriefing` — combines a validated, grounded
`LLMNarrativeOutput` (or the deterministic fallback) with the
deterministically-computed severity/confidence/affected-structures
(`app.incident.severity`) and a fixed, server-side safety disclaimer.

This is the one place all of it comes together, which is exactly why
severity/confidence are computed here rather than trusted from
`narrative` — even if a caller passed in a narrative that *claimed* to
carry those fields (it structurally can't; `LLMNarrativeOutput` has no
such fields — see `app.incident.schemas`), this function would still
never use them.
"""

from typing import Literal

from app.incident.config import IncidentConfig
from app.incident.prompt import PROMPT_VERSION
from app.incident.schemas import IncidentBriefing, IncidentContext, LLMNarrativeOutput
from app.incident.severity import (
    build_affected_structures_summary,
    classify_confidence,
    classify_incident_severity,
)

_DISCLAIMER = (
    "This briefing is AI-assisted decision support, not a verified emergency assessment. "
    "Damage predictions may be wrong. Road risk is a modeled estimate, not a confirmed fact. "
    "Road accessibility has not been independently verified. Real emergency response "
    "decisions must rely on authoritative, verified information — not this summary alone."
)


def assemble_briefing(
    context: IncidentContext,
    narrative: LLMNarrativeOutput,
    source: Literal["provider", "fallback"],
    config: IncidentConfig,
) -> IncidentBriefing:
    return IncidentBriefing(
        analysis_id=context.analysis_id,
        incident_severity=classify_incident_severity(context, config),
        affected_structures=build_affected_structures_summary(context),
        priority_area=narrative.priority_area,
        route_summary=narrative.route_summary,
        key_findings=narrative.key_findings,
        limitations=narrative.limitations,
        confidence=classify_confidence(context, config),
        generated_at=context.generated_at,
        source=source,
        prompt_version=PROMPT_VERSION,
        disclaimer=_DISCLAIMER,
    )

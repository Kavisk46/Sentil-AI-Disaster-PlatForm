"""Deterministic incident-context fixtures for LLM evaluation — including
the Milestone 10 spec's own example
(`severe_damage=14 / moderate_damage=8 / route_distance=4.8 / route_risk=0.31`),
mapped onto the real `app.incident.schemas.IncidentContext`. There is no
literal "moderate_damage" field on `app.ml.schemas.DamageSummary` — the
closest real mapping is `damaged_buildings = severely_damaged + (moderately
damaged, non-severe)`, documented per field below rather than silently
guessed.
"""

from datetime import UTC, datetime
from uuid import uuid4

from app.incident.schemas import DamageContext, IncidentContext, RoadRiskContext, RouteContext
from app.ml.schemas import DamageSummary
from app.routing.schemas import RoutingMode
from app.schemas.analysis import AnalysisStatus

SEVERE_DAMAGE_COUNT = 14
MODERATE_DAMAGE_COUNT = 8
ROUTE_DISTANCE_METERS = 4_800.0
ROUTE_RISK_SCORE = 0.31


def spec_example_context() -> IncidentContext:
    """The Milestone 10 spec's own example context, realized as a real
    `IncidentContext`: 14 severely-damaged buildings, 8 additional
    (moderately) damaged buildings, a 4.8km route with risk 0.31.
    `destroyed=0` since the spec's example does not distinguish destroyed
    from severely-damaged — not invented."""
    total = SEVERE_DAMAGE_COUNT + MODERATE_DAMAGE_COUNT
    return IncidentContext(
        analysis_id=uuid4(),
        analysis_status=AnalysisStatus.COMPLETED,
        damage=DamageContext(
            available=True,
            summary=DamageSummary(
                total_buildings=total,
                damaged_buildings=total,
                severely_damaged=SEVERE_DAMAGE_COUNT,
                destroyed=0,
            ),
            average_confidence=0.87,
            high_priority_structure_ids=[f"bldg-{i}" for i in range(SEVERE_DAMAGE_COUNT)],
        ),
        road_risk=RoadRiskContext(
            available=False, reason="No road network is loaded for this fixture."
        ),
        route=RouteContext(
            available=True,
            selected_mode=RoutingMode.RISK_AWARE,
            selected_distance_meters=ROUTE_DISTANCE_METERS,
            selected_risk_score=ROUTE_RISK_SCORE,
        ),
        generated_at=datetime.now(UTC),
    )


def empty_context() -> IncidentContext:
    """No damage, road-risk, or route data available at all — the
    "insufficient/unavailable" end of the fixture spectrum, used to
    confirm narratives correctly say `"Information unavailable."` rather
    than inventing content."""
    return IncidentContext(
        analysis_id=uuid4(),
        analysis_status=AnalysisStatus.PROCESSING,
        damage=DamageContext(available=False, reason="Analysis is not completed yet."),
        road_risk=RoadRiskContext(available=False, reason="No road network is loaded."),
        route=RouteContext(available=False, reason="No route was requested for this summary."),
        generated_at=datetime.now(UTC),
    )

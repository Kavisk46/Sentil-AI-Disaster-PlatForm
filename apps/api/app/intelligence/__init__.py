"""Disaster Intelligence Core (F2).

This package is the domain model and deterministic decision layer for the
future response-orchestration pipeline described in the project roadmap:

    Disaster observations
            |
    Multimodal intelligence
            |
    Damage / hazard understanding      <- app.ml, app.risk (existing)
            |
    Search-zone prioritization         <- app.intelligence.search_priority
            |
    Resource + capability matching     <- app.intelligence.capability_matching
            |
    Accessibility-aware routing        <- app.routing (existing, reused as-is)
            |
    Recommended response               <- app.intelligence.recommendation
            |
    Evidence + uncertainty             <- app.intelligence.schemas (Evidence, Uncertainty)

F2 implements the domain model (`schemas.py`) and a deterministic,
documented, fully-explainable first version of each intelligence stage.
It deliberately does **not** implement or fabricate any ML prediction: see
`hazard_prediction.py`, whose only constructor always returns
`status=UNAVAILABLE`. Every scoring/matching/recommendation function is a
pure function of real inputs plus a centrally-configured, documented set
of weights (`config.py`, sourced from `app.core.config.Settings`) — the
same "deterministic baseline heuristic, not a validated model" honesty
already established by `app.risk.formula` and `app.incident.severity`.

This package reuses existing types rather than duplicating them:
`app.ml.geospatial.geometry.Geometry`/`CoordinateReferenceSystem` for all
spatial fields, `app.ml.schemas.DamageClass`, `app.ml.geospatial.priority`
for damage-based priority, `app.roads.schemas.AccessibilityStatus`, and
`app.routing.schemas.RouteResult`/`RoutingMode` for route computation —
`app.intelligence` adds no second geometry system, no second routing
engine, and no second damage taxonomy.

`demo_scenario.py` builds one deterministic, explicitly `is_simulated=True`
disaster scenario for exercising the full pipeline end-to-end without a
real incident — see its module docstring for why every entity in it is
clearly marked as demo data, never presented as live.
"""

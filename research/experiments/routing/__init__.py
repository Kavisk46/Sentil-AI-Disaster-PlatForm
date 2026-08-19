"""Routing evaluation: baselines A-D and ablation study A-E over small,
deterministic synthetic road-graph fixtures — never real OSM data, never
a large automatic run (see `research/README.md`, "Do not run huge
experiments automatically").

    A / ablation A  Shortest path        cost = distance
    B / ablation B  Damage-aware         cost = distance + naive damage-density penalty
    C / ablation C  Risk-aware           cost = distance + SentinelAI's real calibrated
                                          road-risk penalty
    -   ablation D  Damage + road risk   both penalties together
    D / ablation E  Full SentinelAI      damage + road risk + hazard (hazard is currently
                                          inert — see below)

See `research.experiments.routing.ablation` for why "damage-aware" and
"risk-aware" are genuinely distinct configurations in this evaluation
(they are not, today, distinct signals inside `app.risk` itself — see
that module's own docstring) and `research.experiments.routing.cost_functions`
for the one new, research-only primitive this milestone adds
(`naive_damage_density_by_edge`) versus what it reuses unmodified from
`app.risk`/`app.routing`.

"Hazard" always has zero effect on cost here: SentinelAI has no hazard
subsystem (see `research.experiments.hazards`), so `use_hazard=True`
configurations are mechanically identical to their non-hazard
counterparts. This is documented, not hidden.
"""

"""SentinelAI research-evaluation framework (Milestone 10).

Answers one question: **does integrating disaster-damage intelligence and
spatial road-risk modeling into graph-based routing reduce modeled
emergency-route risk compared with conventional shortest-path routing,
while keeping added travel distance within an acceptable range?**

This package is a measurement layer bolted onto the real backend
(`apps/api/app`) — it imports and reuses production routing/risk/incident
code directly (`app.routing`, `app.risk`, `app.roads`, `app.ml`,
`app.incident`) rather than re-implementing any of it, and it never
modifies `apps/api/app`. It is not a product feature: nothing here is
imported by, or changes the behavior of, the FastAPI application.

Structure:

    research/
        core/           Shared infrastructure: result schema, reproducibility
                         metadata, metrics (incl. Pareto analysis and a real
                         paired t-test), result storage, report/figure
                         generation, latency measurement.
        experiments/
            routing/    Baselines A-D / ablation A-E over small, deterministic
                         synthetic road-graph fixtures (see routing/fixtures.py
                         — never real OSM data, never a huge automatic run).
            damage/     Precision/recall/F1 (classification) and IoU
                         (localization) utilities, scoped to the task each
                         metric actually applies to.
            hazards/    A screening-framework evaluator for a hazard subsystem
                         SentinelAI does not have yet (see hazards/__init__.py)
                         — evaluates the evaluation harness's own readiness,
                         not any real forecasting accuracy.
            llm/        Groundedness/completeness/unsupported-claim-rate
                         evaluation of `app.incident`'s real narrative
                         pipeline, using the existing `MockLLMProvider`
                         (no external API key, ever).
        configs/        JSON configuration objects selecting a baseline/
                         ablation without touching any code.
        results/        Generated output only (raw/processed/figures) — never
                         committed datasets or model weights; see
                         results/README.md.
        reports/        Generated Markdown/CSV/JSON experiment reports.
        tests/          Deterministic tests for every module above.

See research/README.md for the full research question, hypothesis,
protocol, and — critically — this milestone's scientific-integrity rules:
no fabricated results, no fabricated accuracy, no claimed statistical
significance without an actual test, no claimed real-world emergency
readiness.
"""

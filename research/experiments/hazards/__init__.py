"""Evaluates SentinelAI's hazard subsystem as a screening/assessment
framework.

**SentinelAI has no hazard-prediction subsystem.** Milestone 7 explicitly
excluded hazard/tsunami/flood prediction from scope, and nothing has been
built since. This package therefore does **not** evaluate any real
forecasting accuracy — there is none to evaluate.

What it evaluates instead is the *evaluation harness itself*: given the
interface a future hazard subsystem would need to satisfy
(`HazardAssessor`, in `evaluation.py`) and four required scenario
categories (high-risk evidence, low-risk evidence, missing data,
insufficient data — see `fixtures.py`), does the harness correctly
exercise all four, and does the one real implementation that exists
today (`NullHazardAssessor`, which honestly reports "unavailable" in
every case — because that *is* SentinelAI's real, current
hazard-assessment behavior) behave exactly as documented?

This is deliberately not a claim of hazard-forecasting evaluation in the
operational sense. See `research/README.md`, "Hazard evaluation," for
the full scientific-integrity framing, and do not report `coverage`/
`scenario_correctness` from this package as if they measured predictive
accuracy — they measure harness readiness and the null implementation's
honesty, nothing more.
"""

# SentinelAI Research Evaluation (Milestone 10)

This is a **measurement layer**, not a product feature. Everything under
`research/` imports and reuses the real backend (`apps/api/app`) — it
never changes application behavior, and nothing in `apps/api/app` imports
anything from `research/`.

## 1. Research question

> Can integrating disaster-damage intelligence and spatial road-risk
> modeling into graph-based routing reduce modeled emergency-route risk
> compared with conventional shortest-path routing, while keeping
> additional travel distance within an acceptable range?

## 2. Hypothesis

Routing that accounts for detected damage and SentinelAI's calibrated
road-risk model (`app.risk.formula`) will select routes with lower
accumulated modeled risk than pure shortest-path routing, at some
non-zero but bounded distance cost. This is a **hypothesis to be tested
against measured data**, not a claimed result — see §9 and §11.

## 3. Baselines

| Configuration | Edge cost | Maps to |
| --- | --- | --- |
| A — Shortest path | `distance` | `research.experiments.routing.ablation.SHORTEST_PATH` |
| B — Damage-aware | `distance` + naive damage-proximity penalty | `DAMAGE_AWARE` |
| C — Risk-aware | `distance` + SentinelAI's real calibrated road-risk penalty | `RISK_AWARE` |
| D — Full SentinelAI | damage + road risk + hazard (hazard inert — see §9) | `FULL_SENTINELAI` |

**Why "damage-aware" and "risk-aware" are distinct configurations here,
even though `app.risk` computes road risk *entirely* from damage.**
SentinelAI's real `RoadEdge.risk_score` (`app.risk.formula`) is already a
severity-weighted, distance-decayed, confidence-scaled aggregate of
nearby damage — there is no second, independent "damage" signal at the
road-edge level to reuse for a genuinely different baseline B. Rather
than silently making B and C identical (or inventing a fictitious new
production signal, which Milestone 10 explicitly forbids — "do not add
major product features"), this evaluation defines B's penalty as a
deliberately **naive**, unweighted count of nearby damaged buildings
(`research.experiments.routing.cost_functions.naive_damage_density_by_edge`),
distinct from C's calibrated formula. This makes the routing/damage/hazard
ablation in §5 a genuine measurement of "how much does the sophisticated
spatial risk model add over a crude damage-proximity signal" — not two
names for the same number. See that module's docstring for the full
reasoning.

The routing engine itself (Dijkstra/A*, `app.routing.algorithm`) and the
production risk-adjusted cost formula
(`app.risk.formula.compute_risk_adjusted_cost`) are reused **unmodified**.

## 4. Metrics

All in `research/core/metrics.py` and `research/core/pareto.py`:

- **Route distance** (km) and **route risk** (sum of `RoadEdge.risk_score`
  along the path — `0.0` for an edge never assessed for risk).
- **Risk reduction %** — `(baseline_risk - method_risk) / baseline_risk *
  100`. `None` when baseline risk is `0.0` (undefined, not `0%`).
- **Distance overhead %** — `(method_distance - baseline_distance) /
  baseline_distance * 100`. Raises for a non-positive baseline distance
  (a genuinely degenerate scenario).
- **Runtime** — real `time.perf_counter()` wall-clock milliseconds.
- **Pareto analysis** (`research/core/pareto.py`) — the distance-risk
  Pareto-efficient frontier over a set of routes.
  **`pareto_frontier()` never assumes the lowest-risk route is
  "optimal"** — a route that minimizes risk alone and a route that
  minimizes distance alone can both be Pareto-efficient, because neither
  dominates the other. `describe_tradeoff()` reports the actual, computed
  difference between those two extremes (e.g. "the lowest-risk route
  costs N% more distance") rather than asserting a ranking.
- **Statistical significance** — `research.core.metrics.paired_t_test()`
  is a real, from-scratch (stdlib-only) paired Student's t-test,
  including an exact p-value via the regularized incomplete beta
  function. Nothing in this codebase may claim statistical significance
  without calling this (or an equivalent real test) first — see §9.

## 5. Ablations

| Ablation | Damage | Road risk | Hazard |
| --- | --- | --- | --- |
| A — none | ✗ | ✗ | ✗ |
| B — damage only | ✓ | ✗ | ✗ |
| C — road risk only | ✗ | ✓ | ✗ |
| D — damage + road risk | ✓ | ✓ | ✗ |
| E — damage + road risk + hazard | ✓ | ✓ | ✓ (inert) |

Selected entirely via `research/configs/*.json` — see
`research.experiments.routing.ablation.load_ablation_config()`. Adding or
changing a configuration is always a new/edited JSON file, never a code
change.

## 6. Dataset

**No real dataset is bundled or run automatically.** Routing experiments
use small, fully deterministic *synthetic* road-graph fixtures
(`research/experiments/routing/fixtures.py`) — a 4-node graph with one
synthetic damaged building, never real OSM data or a real disaster site.
Damage-evaluation utilities (`research/experiments/damage/metrics.py`)
are typed against `app.ml.datasets.schemas.BuildingAnnotation` (the same
ground-truth type the xBD dataset abstraction already uses) so they're
ready to run against real annotated data, but no such run happens in this
milestone. See §9 ("Do not run huge experiments automatically").

## 7. Experimental protocol

For each scenario, every configuration under comparison uses:

- the **same** origin/destination,
- the **same** road graph (`research.experiments.routing.run_experiment.run_scenario`
  builds one risk-assessed graph per scenario and reuses it for every
  configuration — never a different graph per configuration),
- the **same** disaster evidence (the scenario's fixed set of damaged
  buildings).

`run_scenario()` measures every configuration, then computes
`risk_reduction_percent`/`distance_overhead_percent` relative to one
designated baseline's *own measured result for that same scenario* —
never a different scenario or a different graph instance.

## 8. Reproducibility

Every `ExperimentResult` (`research/core/schemas.py`) carries a
`ReproducibilityMetadata` block
(`research/core/reproducibility.py`) with: `experiment_id`, `timestamp`,
`dataset_version`, `scenario_id`, `model_version`, `routing_configuration`,
`risk_configuration`, `random_seed`, `hardware`, `software`.

**Deliberately excluded, always**: hostname (`platform.node()` is never
called — see `test_reproducibility.py`), username, IP/MAC address, and
absolute file paths. `hardware` is limited to `platform.system()`,
`platform.release()`, `platform.machine()`, and `os.cpu_count()`.
`software` records installed package versions (`fastapi`, `pydantic`,
`torch`, `sentinelai-api`) via `importlib.metadata`, never a hand-typed
version string.

## 9. Limitations

- **Hazard is inert.** SentinelAI has no hazard-prediction subsystem
  (Milestone 7 explicitly excluded it, and nothing has changed since).
  Every `use_hazard=True` configuration is mechanically identical to its
  non-hazard counterpart. `research/experiments/hazards/` evaluates the
  *evaluation harness's own readiness* for a future hazard subsystem —
  coverage of the four required evidence categories and the correctness
  of the one real implementation (`NullHazardAssessor`, which honestly
  reports "unavailable" always) — never real forecasting accuracy. Do
  not read `coverage`/`scenario_correctness` from that package as a
  claim about hazard prediction quality.
- **The road-risk model is an uncalibrated heuristic** (`app.risk.formula`
  — severity × exponential distance decay × confidence, summed and
  capped). It has not been validated against real disaster outcomes. Any
  "risk reduction" this framework measures is a reduction in *this
  heuristic's score*, not a validated reduction in real-world danger.
- **No huge experiments run automatically.** This milestone delivers the
  framework and small, deterministic fixtures only, per the milestone
  spec's own instruction. Real experiments (larger road graphs, real
  imagery, real damage predictions) are run manually, later, by a human
  reviewing this framework first.
- **Damage-evaluation metrics are unwired to any real run.**
  `research/experiments/damage/metrics.py` provides correct, correctly-scoped
  utilities (precision/recall/F1 for classification; IoU for
  localization) but nothing in this milestone calls them against a real
  model's predictions or the xBD ground truth — no real damage-detection
  model exists yet in this codebase (`app.ml.localizer.UnavailableBuildingLocalizer`).
- **LLM evaluation is scoped to the mock/deterministic providers.**
  `research/experiments/llm/` never calls a real LLM API (no external key,
  no network) — it evaluates `app.incident`'s grounding filter and
  deterministic fallback, which is exactly what production actually runs
  by default (`Settings.LLM_PROVIDER = "deterministic"`).
- **Latency measurements reflect this dev environment on tiny synthetic
  fixtures** (`research/core/latency.py`,
  `research/tests/test_pipeline_latency.py`) — not production hardware,
  not real imagery, not a claim about production responsiveness.
- **Statistical tests require real paired data.** `paired_t_test()` is a
  real implementation, but running it meaningfully requires multiple real
  scenarios — the single synthetic fixture in this milestone is not a
  sample large enough to draw a real conclusion from. No result in this
  milestone claims statistical significance.
- **No real-world emergency readiness is claimed anywhere in this
  package.** See `research/core/latency.py` and every `hazards`/`llm`
  module docstring for the explicit disclaimers this rule requires.

## 10. Future experiments

- Run the full baseline/ablation matrix (§3, §5) against a real, larger
  road graph (e.g. a real OSM extract via `app.roads.osm_source`) and
  real xBD-derived damage predictions, once a real building-localization
  model exists.
- Run `paired_t_test()` across a real multi-scenario sample to test
  whether a measured risk reduction is statistically significant, not
  just directionally present.
- Evaluate `research.experiments.damage.metrics` against real
  predictions and xBD ground truth once a trained damage-classification
  model exists.
- Re-evaluate `research/experiments/hazards/` against a real hazard
  subsystem, if and when one is built — the harness (interface,
  scenario categories, correctness check) is designed to need no changes
  when that happens, only a real `HazardAssessor` implementation and new
  fixtures with genuine `expected_available=True` cases.
- Extend the LLM evaluation to a real LLM provider (`AnthropicLLMProvider`)
  under an opt-in, explicitly-keyed test lane — never as part of the
  default, no-network test suite.

---

## Running the framework

No new virtual environment: `research/` reuses `apps/api/.venv` (which
already has `pydantic`, `pytest`, `ruff`, `mypy`, and the editable-installed
`sentinelai-api` package that makes `import app.*` work from anywhere).

```bash
# From the repository root:
apps/api/.venv/Scripts/python.exe -m pytest research/tests
apps/api/.venv/Scripts/python.exe -m ruff check research
apps/api/.venv/Scripts/python.exe -m mypy research --config-file research/pyproject.toml
```

All existing `apps/api` tests continue to pass unchanged — this milestone
adds a new, separate package and touches no file under `apps/api/app`.

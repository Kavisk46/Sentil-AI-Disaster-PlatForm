# Future Work

This document tracks research directions that extend beyond SentinelAI's
core platform (Phases 0–8) and are formally scoped under **Phase 9 —
Research Extensions** in [`PROJECT_ROADMAP.md`](../../PROJECT_ROADMAP.md).
Each direction below is a candidate for future investment, not a committed
deliverable of the core platform.

## Multi-Modal Damage Assessment

Combine optical aerial imagery with Synthetic Aperture Radar (SAR) data to
enable damage assessment that is not blocked by cloud cover, smoke, or
nighttime conditions — all common during active disaster response. This
requires investigating fusion approaches for combining optical and SAR
signals rather than treating them as independent inputs.

## Change Detection with Pre/Post Imagery Pairs

Extend damage detection to directly compare pre-disaster and post-disaster
imagery of the same location, isolating damage with higher precision than
single-image classification (see [`literature-review.md`](literature-review.md)).
This requires establishing a reliable source of recent pre-disaster imagery
for arbitrary regions, which is not guaranteed to be available in every
scenario.

## Edge Inference for Field Deployment

Investigate running a reduced-footprint version of the damage detection
models directly on field hardware (e.g., on a drone operator's ground
station), so preliminary assessments are available even when connectivity to
a central backend is degraded or unavailable — a common condition
immediately after a disaster.

## Federated Learning Across Response Organizations

Explore federated learning approaches that let multiple response
organizations contribute to improving shared detection models without
centralizing their raw, potentially sensitive imagery. This would allow
SentinelAI's models to benefit from a broader base of real-world deployments
than any single organization's data could provide alone.

## Uncertainty-Aware Routing

Extend the routing subsystem to communicate the confidence of a computed
route rather than presenting a single deterministic path, surfacing where
hazard detections are less certain so responders can make an informed
judgment call rather than trusting an opaque recommendation.

## Human-in-the-Loop Model Feedback

Design a feedback mechanism that lets field-verified damage assessments
(i.e., what responders actually found on the ground) flow back into model
evaluation and retraining, so the platform's accuracy improves from real
deployments over time rather than remaining fixed at its initial training
data.

## Multimodal Disaster-Response Intelligence: Baseline Registry

**Research question:** How can multimodal AI prioritize disaster-response
actions under uncertainty, incomplete information, inaccessible
infrastructure, and changing hazards?

Milestone F2 (`app/intelligence/`, see
[`docs/architecture/intelligence.md`](../architecture/intelligence.md))
implements the **deterministic baseline/control system** this question
will eventually be evaluated against: a documented, uncalibrated,
rule-based search-priority scorer, capability matcher, and
recommendation engine — no ML model, no LLM. Future work can compare it
against progressively richer systems using the following registry:

| Baseline | Description |
|---|---|
| **B0** | No intelligence/ranking — resources dispatched with no prioritization at all. |
| **B1** | Damage-only prioritization — rank by `app.ml.geospatial.priority.compute_damage_priority` alone (the pre-F2 building-priority signal), no accessibility/population/evidence factors. |
| **B2** | Damage + accessibility — F2's `search_priority` scorer with `population_exposure_weight`/`evidence_strength_weight` set to `0` (see `SearchPriorityConfig`, `app/intelligence/config.py`). |
| **B3** | Damage + accessibility + resource capability — **F2 as implemented today**: the full deterministic pipeline (`search_priority` -> `capability_matching` -> `recommendation`). |
| **B4** | Full multimodal response intelligence — a real ML/LLM-augmented version of any F2 stage (see `docs/architecture/intelligence.md`, "Future ML/LLM integration," for the exact extension points each stage already exposes). |

**No experiments have been run and no performance claims are made for
any baseline in this registry as of Milestone F2/F3.** B0–B3 are
implementable today from existing code; B4 requires the ML/LLM work this
document's other sections describe.

**Milestone F3** (`app/intelligence/analysis_adapter.py`, see
[`docs/architecture/intelligence.md`](../architecture/intelligence.md),
"Milestone F3") is what makes B1–B3 runnable against **real analysis
input** rather than only the hand-authored demo scenario — it adapts a
completed analysis's actual damage classifications and road-risk
assessment into the same `AffectedArea`/`Infrastructure` inputs the
registry's baselines already consume, through F2's engines, unmodified.
This does not change the registry itself (still no experiments run, no
performance claims made) — it removes what was previously the only
practical blocker to running B1–B3 against a real uploaded image instead
of a synthetic fixture.

### Future evaluation metrics

Once a real evaluation is scoped, candidate metrics per baseline
include:

- **Search-zone ranking quality** — agreement between ranked zones and
  ground-truth priority (e.g. rank correlation against verified
  outcomes, once such a dataset exists).
- **Route feasibility** — fraction of recommended routes that are
  actually traversable given real, contemporaneous road/hazard state.
- **Resource assignment feasibility** — fraction of
  capability-matching-eligible assignments that a real deployment could
  actually execute (capability, availability, and reachability
  double-checked against ground truth).
- **Recommendation correctness** — agreement between the engine's
  recommended action and what a qualified human responder would choose
  given the same inputs.
- **Evidence traceability** — whether every recommendation's
  `supporting_evidence` genuinely accounts for the recommendation (not
  just present, but relevant and sufficient).
- **Calibration/uncertainty quality** — for any baseline that produces a
  numeric confidence (B4 candidates only — B0–B3 never do, by design),
  whether stated confidence matches empirical accuracy.
- **Latency** — end-to-end time from input to recommendation, relevant
  once a baseline involves a real model inference call (B4).

This document records the research direction and metric candidates
only. Running these evaluations, collecting ground-truth outcome data,
and reporting results are explicitly out of scope for Milestone F2.

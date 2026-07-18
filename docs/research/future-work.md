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

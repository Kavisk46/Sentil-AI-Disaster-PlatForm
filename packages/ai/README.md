# SentinelAI AI Engine

This directory will contain generative AI components (operational briefing
generation) and, potentially, an independently-deployed computer vision
service if damage detection is ever split out of the backend.

**The damage-detection architecture and its first concrete (untrained)
model adapters — model interfaces, typed result schemas, a two-stage
building-localization + damage-classification pipeline, and the
preprocessing/postprocessing/evaluation code around it — live in
[`apps/api/app/ml/`](../../apps/api/app/ml/) instead**, since they're
currently implemented as part of the backend service, not a standalone
deployment. See
[`apps/api/README.md`](../../apps/api/README.md#ml-architecture-milestones-3a-and-3c)
for that architecture, and
[`docs/architecture/ai-engine.md`](../../docs/architecture/ai-engine.md)
for how it fits the platform overall.

This package (`packages/ai`) is reserved here alongside the monorepo's
JS/TS packages for discoverability, but is not part of the npm workspace —
it will gain its own `pyproject.toml` if/when a generative-briefing
component is implemented, or if training-only dependencies (a GPU-oriented
training script, an augmentation library, ...) grow large enough to want
separating from the deployed API's own dependency tree, building on the
research basis documented in
[`docs/research/literature-review.md`](../../docs/research/literature-review.md).

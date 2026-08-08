# SentinelAI AI Engine

This directory will contain the computer vision and generative AI components
responsible for damage detection, infrastructure impact classification, and
operational briefing generation.

It is a Python package (PyTorch-based), reserved here as `packages/ai`
alongside the monorepo's JS/TS packages for discoverability, but it is not
part of the npm workspace — it will gain its own `pyproject.toml` when
implementation begins.

No model or pipeline code has been added yet. Implementation begins in
**Phase 4 — AI Integration** of [`PROJECT_ROADMAP.md`](../../PROJECT_ROADMAP.md),
building on the research basis documented in
[`docs/research/literature-review.md`](../../docs/research/literature-review.md).

For the intended architecture and how this engine integrates with the
backend and routing subsystem, see
[`docs/architecture/ai-engine.md`](../../docs/architecture/ai-engine.md).

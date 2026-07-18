# AI Engine Architecture

The AI engine is responsible for turning raw aerial imagery into structured
damage assessments, and for turning those structured assessments into
readable operational briefings.

## Responsibilities

- **Damage detection** — identify and classify structural damage severity
  from aerial imagery.
- **Infrastructure impact classification** — identify affected roads,
  bridges, utilities, and critical facilities within processed imagery.
- **Briefing generation** — synthesize detected findings into a concise,
  decision-ready situation report using a generative language model.

## Intended Structure

The AI engine is a Python service built on PyTorch for computer vision
inference, with a separate generative component responsible for briefing
synthesis. Detection and generation are treated as independently swappable
stages behind a stable internal interface, so improved models can be adopted
without requiring changes to the backend or frontend.

Planned top-level organization within `ai/`:

- **Preprocessing** — imagery normalization, tiling, and georeferencing prior
  to inference.
- **Detection models** — damage classification and infrastructure detection
  models and their inference pipelines.
- **Briefing generation** — prompt construction and generation logic that
  converts structured detection output into narrative briefings.
- **Evaluation** — benchmarks and held-out evaluation sets used to measure
  model accuracy over time.

## Key Interactions with Other Subsystems

- Receives imagery and job requests from the [backend](backend.md) and
  returns structured detection results for persistence.
- Detection output feeds both the [routing subsystem](routing.md) (as
  hazard input) and the briefing generation stage.
- Never communicates directly with the frontend; all output is persisted and
  served through the backend API.

## Research Basis

The modeling approach for this subsystem is informed by the survey in
[`docs/research/literature-review.md`](../research/literature-review.md), and
forward-looking extensions (multi-modal input, change detection, federated
learning) are tracked in
[`docs/research/future-work.md`](../research/future-work.md).

## Status

AI engine implementation begins in **Phase 4** of [`PROJECT_ROADMAP.md`](../../PROJECT_ROADMAP.md). This document will be expanded with concrete model architectures and evaluation methodology as that phase begins.

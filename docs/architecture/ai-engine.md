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

Damage-detection's architecture — the model interfaces, typed result
contracts, preprocessing/postprocessing, and (as of Milestone 3C) its
first concrete two-stage building-localization + damage-classification
adapters — was established in `apps/api/app/ml/` rather than `packages/ai/`,
since it is currently implemented as part of the backend service, not a
standalone deployment. See
[`apps/api/README.md`](../../apps/api/README.md#ml-architecture-milestones-3a-and-3c)
for the concrete architecture; `packages/ai/` remains reserved for the
generative-briefing component and for a possible future split into an
independently deployed inference/training service (e.g. once real GPU
training introduces dependencies that shouldn't bloat the deployed API).

Planned top-level organization within `packages/ai/`:

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

The damage-detection *architecture and its first concrete adapters* exist
in `apps/api/app/ml/` — a two-stage design (building localization, then
damage classification, composed via `TwoStageDamageModel`). **No model has
been trained.** Stage 1 (building localization) has no implementation
beyond its interface — no off-the-shelf pretrained detector has a
"building" class to start from. Stage 2 (damage classification,
`TorchDamageClassifier`, a ResNet18 baseline) is real, working inference
code with no fine-tuned checkpoint loaded. Both fail loudly rather than
fabricating a result; see
[`apps/api/README.md`](../../apps/api/README.md#ml-architecture-milestones-3a-and-3c)
for the full architecture, the model-selection rationale, and why.

The dataset pipeline that a future training run will consume — parsing and
validating the [xBD](https://arxiv.org/abs/1911.09296) dataset, and
normalizing its labels into the same `DamageClass` taxonomy the model
interfaces already use — exists in `apps/api/app/ml/datasets/`. No dataset
is downloaded or committed by this repository; see
[`apps/api/README.md`](../../apps/api/README.md#dataset-pipeline-milestone-3b)
for what xBD is, why it fits, and where to place it locally. No model
training happens yet, and none is planned to happen on this (CPU-only)
development machine — see
[`apps/api/README.md`](../../apps/api/README.md#training-vs-inference) for
where it will.

Full AI engine implementation (a real, trained model; briefing generation)
continues in **Phase 4** of [`PROJECT_ROADMAP.md`](../../PROJECT_ROADMAP.md).

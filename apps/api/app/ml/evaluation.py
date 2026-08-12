"""Evaluation interface for the damage-classification stage.

Pure Python — precision/recall/F1/confusion-matrix computation for a fixed
4-class problem doesn't need a dependency like scikit-learn to be correct
(see `apps/api/README.md`).

Deliberately refuses to compute metrics on empty input rather than
returning a degenerate, misleading zero-filled result — see
`EvaluationNotPerformedError`. No trained model or evaluation dataset
exists yet, so nothing in this codebase currently calls this module with
real predictions; it exists so a future training run has an evaluation
harness ready on day one, using the same `DamageClass` taxonomy and the
xBD dataset abstraction (`app.ml.datasets`) rather than a second one.
"""

from collections.abc import Sequence

from pydantic import BaseModel, Field

from app.ml.schemas import DamageClass

ConfusionMatrix = dict[str, dict[str, int]]


class EvaluationNotPerformedError(RuntimeError):
    """Raised instead of computing metrics on empty/invalid input.

    Reporting precision/recall/F1 for zero examples would be a fabricated
    metric no different in spirit than a fabricated prediction — this
    class exists so `evaluate_classification` fails clearly rather than
    quietly returning 0.0s that could be mistaken for a real (bad) score.
    """


class ClassMetrics(BaseModel):
    """Precision/recall/F1 for one `DamageClass`, plus its support (the
    number of ground-truth instances of that class)."""

    damage_class: DamageClass
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)
    support: int = Field(ge=0)


class EvaluationResult(BaseModel):
    """Result of comparing predictions against ground truth.

    `macro_f1` (the unweighted mean of per-class F1) is the headline
    metric — it weights all four damage classes equally rather than being
    dominated by `no_damage`, which is typically the majority class in
    xBD. `confusion_matrix` is keyed `[true_class][predicted_class] ->
    count`.
    """

    per_class: list[ClassMetrics]
    macro_f1: float = Field(ge=0.0, le=1.0)
    confusion_matrix: ConfusionMatrix
    num_predictions: int = Field(ge=0)
    num_ground_truth: int = Field(ge=0)


def evaluate_classification(
    predicted: Sequence[DamageClass], true: Sequence[DamageClass]
) -> EvaluationResult:
    """Compute per-class precision/recall/F1, macro-F1, and a confusion
    matrix for index-aligned prediction/ground-truth lists.

    Index-aligned (not IoU-matched) because this evaluates the
    *classification* stage in isolation, given a known set of buildings in
    a known order — exactly xBD's ground-truth polygons, matching this
    project's v1 scope (see `apps/api/README.md`). Detection-quality
    evaluation (matching predicted to ground-truth boxes via
    `BoundingBox.iou`) is a separate concern for once Stage 1 produces
    real locations.
    """
    if not predicted or not true:
        raise EvaluationNotPerformedError(
            "No predictions or ground truth supplied — evaluation has not "
            "been performed."
        )
    if len(predicted) != len(true):
        raise ValueError(
            f"predicted ({len(predicted)}) and true ({len(true)}) must be the "
            "same length: each index is one building's prediction and ground "
            "truth."
        )

    classes = list(DamageClass)
    confusion: ConfusionMatrix = {
        a.value: dict.fromkeys((p.value for p in classes), 0) for a in classes
    }
    for predicted_class, true_class in zip(predicted, true, strict=True):
        confusion[true_class.value][predicted_class.value] += 1

    per_class: list[ClassMetrics] = []
    for damage_class in classes:
        true_positives = confusion[damage_class.value][damage_class.value]
        false_positives = sum(
            confusion[other.value][damage_class.value] for other in classes if other != damage_class
        )
        false_negatives = sum(
            confusion[damage_class.value][other.value] for other in classes if other != damage_class
        )
        support = sum(confusion[damage_class.value].values())

        precision = (
            true_positives / (true_positives + false_positives)
            if (true_positives + false_positives) > 0
            else 0.0
        )
        recall = (
            true_positives / (true_positives + false_negatives)
            if (true_positives + false_negatives) > 0
            else 0.0
        )
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        per_class.append(
            ClassMetrics(
                damage_class=damage_class,
                precision=precision,
                recall=recall,
                f1=f1,
                support=support,
            )
        )

    macro_f1 = sum(metrics.f1 for metrics in per_class) / len(per_class)

    return EvaluationResult(
        per_class=per_class,
        macro_f1=macro_f1,
        confusion_matrix=confusion,
        num_predictions=len(predicted),
        num_ground_truth=len(true),
    )

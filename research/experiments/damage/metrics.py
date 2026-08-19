"""Damage-model evaluation metrics for two distinct prediction tasks —
**this module never conflates them**:

1. **Classification** — did the model assign the right `DamageClass` to a
   building? Measured by `precision`/`recall`/`f1_score`, computed from
   per-class confusion counts (`confusion_counts_by_class`).
2. **Localization** — did the model find the building in the right place
   at all? Measured by intersection-over-union
   (`intersection_over_union`/`mean_iou`) between predicted and
   ground-truth `app.ml.spatial.BoundingBox` instances.

Computing IoU against damage-class labels, or precision/recall against
raw bounding-box overlap, would be an inappropriate use of each metric —
this module keeps the two tasks structurally separate (different
functions, different input types) so that mistake isn't possible by
accident. No metric here is calculated automatically against any real
dataset; these are utilities for when real predictions and ground truth
exist to compare.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.ml.datasets.schemas import BuildingAnnotation
from app.ml.schemas import DamageClass
from app.ml.spatial import BoundingBox

# ---------------------------------------------------------------------------
# Task 1: classification (predicted DamageClass vs. ground-truth DamageClass)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClassificationCounts:
    """Confusion-matrix counts for one `DamageClass`, within a
    multi-class classification evaluation."""

    true_positive: int
    false_positive: int
    false_negative: int


def precision(counts: ClassificationCounts) -> float | None:
    """CLASSIFICATION task: of everything predicted as this class, what
    fraction was actually this class. `None` when nothing was predicted
    as this class — undefined, not `0.0`."""
    denominator = counts.true_positive + counts.false_positive
    if denominator == 0:
        return None
    return counts.true_positive / denominator


def recall(counts: ClassificationCounts) -> float | None:
    """CLASSIFICATION task: of everything actually this class, what
    fraction was correctly predicted. `None` when this class never
    appears in the ground truth — undefined, not `0.0`."""
    denominator = counts.true_positive + counts.false_negative
    if denominator == 0:
        return None
    return counts.true_positive / denominator


def f1_score(precision_value: float | None, recall_value: float | None) -> float | None:
    """CLASSIFICATION task: the harmonic mean of precision and recall.
    `None` if either input is `None`, or if both are `0.0` (the harmonic
    mean of two zeros is undefined, not `0.0`)."""
    if precision_value is None or recall_value is None:
        return None
    denominator = precision_value + recall_value
    if denominator == 0.0:
        return None
    return 2 * precision_value * recall_value / denominator


def confusion_counts_by_class(
    predictions: Mapping[str, DamageClass], ground_truth: Sequence[BuildingAnnotation]
) -> dict[DamageClass, ClassificationCounts]:
    """Builds per-class `ClassificationCounts` for the CLASSIFICATION
    task, matching `predictions` (`building_id -> predicted DamageClass`)
    to `ground_truth` (`app.ml.datasets.schemas.BuildingAnnotation`) by
    `building_id`. A ground-truth building with no matching prediction
    counts as a false negative for its true class; a prediction with no
    matching ground-truth building is excluded (there is nothing to
    score it against).
    """
    truth_by_id = {annotation.building_id: annotation.damage_class for annotation in ground_truth}
    true_positive: Counter[DamageClass] = Counter()
    false_positive: Counter[DamageClass] = Counter()
    false_negative: Counter[DamageClass] = Counter()

    for building_id, predicted_class in predictions.items():
        actual_class = truth_by_id.get(building_id)
        if actual_class is None:
            continue
        if predicted_class == actual_class:
            true_positive[predicted_class] += 1
        else:
            false_positive[predicted_class] += 1
            false_negative[actual_class] += 1

    for building_id, actual_class in truth_by_id.items():
        if building_id not in predictions:
            false_negative[actual_class] += 1

    return {
        damage_class: ClassificationCounts(
            true_positive=true_positive[damage_class],
            false_positive=false_positive[damage_class],
            false_negative=false_negative[damage_class],
        )
        for damage_class in DamageClass
    }


# ---------------------------------------------------------------------------
# Task 2: localization (predicted BoundingBox vs. ground-truth BoundingBox)
# ---------------------------------------------------------------------------


def intersection_over_union(predicted_box: BoundingBox, ground_truth_box: BoundingBox) -> float:
    """LOCALIZATION task only — how well a predicted bounding box
    overlaps a ground-truth one, independent of any damage
    classification. Delegates to `BoundingBox.iou()` (`app.ml.spatial`),
    which names this evaluation module as its intended consumer in its
    own docstring — not a second, duplicate implementation.
    """
    return predicted_box.iou(ground_truth_box)


def mean_iou(pairs: Sequence[tuple[BoundingBox, BoundingBox]]) -> float | None:
    """LOCALIZATION task: mean IoU over `(predicted, ground_truth)` box
    pairs. `None` for an empty sequence — undefined, not `0.0`."""
    if not pairs:
        return None
    return sum(predicted.iou(truth) for predicted, truth in pairs) / len(pairs)

import pytest
from app.ml.datasets.schemas import BuildingAnnotation
from app.ml.schemas import DamageClass
from app.ml.spatial import BoundingBox

from research.experiments.damage.metrics import (
    ClassificationCounts,
    confusion_counts_by_class,
    f1_score,
    intersection_over_union,
    mean_iou,
    precision,
    recall,
)


def test_precision_and_recall_computed_from_counts() -> None:
    counts = ClassificationCounts(true_positive=8, false_positive=2, false_negative=4)
    assert precision(counts) == pytest.approx(0.8)
    assert recall(counts) == pytest.approx(2 / 3)


def test_precision_is_none_when_nothing_was_predicted_as_this_class() -> None:
    counts = ClassificationCounts(true_positive=0, false_positive=0, false_negative=5)
    assert precision(counts) is None


def test_recall_is_none_when_class_never_appears_in_ground_truth() -> None:
    counts = ClassificationCounts(true_positive=0, false_positive=3, false_negative=0)
    assert recall(counts) is None


def test_f1_score_harmonic_mean() -> None:
    assert f1_score(0.8, 2 / 3) == pytest.approx(2 * 0.8 * (2 / 3) / (0.8 + 2 / 3))


def test_f1_score_is_none_if_either_input_is_none() -> None:
    assert f1_score(None, 0.5) is None
    assert f1_score(0.5, None) is None


def test_f1_score_is_none_for_two_zeros() -> None:
    assert f1_score(0.0, 0.0) is None


def test_confusion_counts_by_class_matches_predictions_to_ground_truth_by_id() -> None:
    ground_truth = [
        BuildingAnnotation(
            building_id="b1", polygon_wkt="POLYGON EMPTY", damage_class=DamageClass.DESTROYED
        ),
        BuildingAnnotation(
            building_id="b2", polygon_wkt="POLYGON EMPTY", damage_class=DamageClass.MINOR
        ),
        BuildingAnnotation(
            building_id="b3", polygon_wkt="POLYGON EMPTY", damage_class=DamageClass.DESTROYED
        ),
    ]
    predictions = {
        "b1": DamageClass.DESTROYED,  # correct
        "b2": DamageClass.MAJOR,  # wrong: predicted major, actually minor
        # b3 has no prediction at all -> false negative for DESTROYED
        "b4": DamageClass.MINOR,  # no ground truth -> ignored
    }

    counts = confusion_counts_by_class(predictions, ground_truth)

    assert counts[DamageClass.DESTROYED] == ClassificationCounts(
        true_positive=1, false_positive=0, false_negative=1
    )
    assert counts[DamageClass.MAJOR] == ClassificationCounts(
        true_positive=0, false_positive=1, false_negative=0
    )
    assert counts[DamageClass.MINOR] == ClassificationCounts(
        true_positive=0, false_positive=0, false_negative=1
    )
    assert counts[DamageClass.NO_DAMAGE] == ClassificationCounts(
        true_positive=0, false_positive=0, false_negative=0
    )


def test_intersection_over_union_of_identical_boxes_is_one() -> None:
    box = BoundingBox(x_min=0, y_min=0, x_max=10, y_max=10)
    assert intersection_over_union(box, box) == pytest.approx(1.0)


def test_intersection_over_union_of_disjoint_boxes_is_zero() -> None:
    a = BoundingBox(x_min=0, y_min=0, x_max=5, y_max=5)
    b = BoundingBox(x_min=10, y_min=10, x_max=15, y_max=15)
    assert intersection_over_union(a, b) == 0.0


def test_intersection_over_union_of_partially_overlapping_boxes() -> None:
    a = BoundingBox(x_min=0, y_min=0, x_max=10, y_max=10)  # area 100
    b = BoundingBox(x_min=5, y_min=0, x_max=15, y_max=10)  # area 100, overlap 50
    # union = 100 + 100 - 50 = 150
    assert intersection_over_union(a, b) == pytest.approx(50 / 150)


def test_mean_iou_averages_over_pairs() -> None:
    identical = BoundingBox(x_min=0, y_min=0, x_max=10, y_max=10)
    disjoint_a = BoundingBox(x_min=0, y_min=0, x_max=5, y_max=5)
    disjoint_b = BoundingBox(x_min=10, y_min=10, x_max=15, y_max=15)

    result = mean_iou([(identical, identical), (disjoint_a, disjoint_b)])

    assert result == pytest.approx(0.5)


def test_mean_iou_is_none_for_empty_input() -> None:
    assert mean_iou([]) is None

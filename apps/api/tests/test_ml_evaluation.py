import pytest

from app.ml.evaluation import EvaluationNotPerformedError, evaluate_classification
from app.ml.schemas import DamageClass


def test_perfect_predictions_yield_macro_f1_of_one() -> None:
    true = [DamageClass.NO_DAMAGE, DamageClass.MINOR, DamageClass.MAJOR, DamageClass.DESTROYED]

    result = evaluate_classification(predicted=true, true=true)

    assert result.macro_f1 == 1.0
    assert all(m.precision == 1.0 and m.recall == 1.0 for m in result.per_class)


def test_empty_predictions_raise_rather_than_report_fabricated_metrics() -> None:
    with pytest.raises(EvaluationNotPerformedError):
        evaluate_classification(predicted=[], true=[])


def test_mismatched_lengths_raise_value_error() -> None:
    with pytest.raises(ValueError, match="same length"):
        evaluate_classification(
            predicted=[DamageClass.NO_DAMAGE],
            true=[DamageClass.NO_DAMAGE, DamageClass.MINOR],
        )


def test_confusion_matrix_counts_correctly() -> None:
    true = [DamageClass.NO_DAMAGE, DamageClass.NO_DAMAGE, DamageClass.DESTROYED]
    predicted = [DamageClass.NO_DAMAGE, DamageClass.MINOR, DamageClass.DESTROYED]

    result = evaluate_classification(predicted=predicted, true=true)

    assert result.confusion_matrix["no_damage"]["no_damage"] == 1
    assert result.confusion_matrix["no_damage"]["minor"] == 1
    assert result.confusion_matrix["destroyed"]["destroyed"] == 1
    assert result.num_predictions == 3
    assert result.num_ground_truth == 3


def test_per_class_support_reflects_ground_truth_counts() -> None:
    true = [DamageClass.NO_DAMAGE, DamageClass.NO_DAMAGE, DamageClass.MINOR]
    predicted = [DamageClass.NO_DAMAGE, DamageClass.NO_DAMAGE, DamageClass.MINOR]

    result = evaluate_classification(predicted=predicted, true=true)

    support_by_class = {m.damage_class: m.support for m in result.per_class}
    assert support_by_class[DamageClass.NO_DAMAGE] == 2
    assert support_by_class[DamageClass.MINOR] == 1
    assert support_by_class[DamageClass.MAJOR] == 0
    assert support_by_class[DamageClass.DESTROYED] == 0


def test_worst_case_predictions_yield_low_macro_f1() -> None:
    true = [DamageClass.NO_DAMAGE] * 4
    predicted = [DamageClass.DESTROYED] * 4

    result = evaluate_classification(predicted=predicted, true=true)

    assert result.macro_f1 < 0.5

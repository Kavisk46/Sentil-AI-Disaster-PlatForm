import math

import pytest

from research.core.metrics import (
    distance_overhead_percent,
    paired_t_test,
    regularized_incomplete_beta,
    risk_reduction_percent,
    student_t_two_tailed_p_value,
)


def test_risk_reduction_percent_computes_real_percentage() -> None:
    assert risk_reduction_percent(0.81, 0.31) == pytest.approx(61.728395, rel=1e-6)


def test_risk_reduction_percent_is_none_for_zero_baseline() -> None:
    """Zero baseline risk handling: reduction relative to zero is undefined."""
    assert risk_reduction_percent(0.0, 0.0) is None
    assert risk_reduction_percent(0.0, 0.5) is None


def test_distance_overhead_percent_computes_real_percentage() -> None:
    assert distance_overhead_percent(4.2, 4.8) == pytest.approx(14.285714, rel=1e-6)


def test_distance_overhead_percent_rejects_non_positive_baseline() -> None:
    with pytest.raises(ValueError, match="positive baseline_distance"):
        distance_overhead_percent(0.0, 1.0)
    with pytest.raises(ValueError, match="positive baseline_distance"):
        distance_overhead_percent(-1.0, 1.0)


# ---------------------------------------------------------------------------
# Regularized incomplete beta / Student's t p-value — verified against
# self-checking mathematical identities, not just "looks plausible."
# ---------------------------------------------------------------------------


def test_regularized_incomplete_beta_boundary_values() -> None:
    assert regularized_incomplete_beta(2.0, 3.0, 0.0) == 0.0
    assert regularized_incomplete_beta(2.0, 3.0, 1.0) == 1.0


def test_regularized_incomplete_beta_symmetric_case_at_half() -> None:
    """I_0.5(a, a) == 0.5 exactly, for any a>0 — a symmetry identity of
    the incomplete beta function, independent of any external table."""
    assert regularized_incomplete_beta(3.0, 3.0, 0.5) == pytest.approx(0.5, abs=1e-9)


def test_student_t_p_value_is_one_at_t_zero() -> None:
    assert student_t_two_tailed_p_value(0.0, degrees_of_freedom=10) == pytest.approx(1.0, abs=1e-9)


def test_student_t_p_value_matches_cauchy_identity_at_df_one() -> None:
    """For df=1 the t-distribution is the standard Cauchy distribution,
    with an exact closed form: P(|T| > t) = 1 - (2/pi) * atan(t). Checked
    independently of the incomplete-beta implementation."""
    t_statistic = 1.0
    expected = 1.0 - (2.0 / math.pi) * math.atan(t_statistic)
    assert student_t_two_tailed_p_value(t_statistic, degrees_of_freedom=1) == pytest.approx(
        expected, rel=1e-6
    )


def test_student_t_p_value_near_known_critical_value() -> None:
    """t=2.228, df=10 is the standard two-tailed alpha=0.05 critical value
    from published Student's t tables."""
    p_value = student_t_two_tailed_p_value(2.228, degrees_of_freedom=10)
    assert p_value == pytest.approx(0.05, abs=0.002)


def test_student_t_p_value_rejects_non_positive_degrees_of_freedom() -> None:
    with pytest.raises(ValueError, match="degrees_of_freedom must be positive"):
        student_t_two_tailed_p_value(1.0, degrees_of_freedom=0)


# ---------------------------------------------------------------------------
# paired_t_test
# ---------------------------------------------------------------------------


def test_paired_t_test_detects_a_consistent_reduction() -> None:
    baseline = [0.81, 0.72, 0.65, 0.90, 0.55]
    method = [0.31, 0.28, 0.20, 0.40, 0.15]

    result = paired_t_test(baseline, method)

    assert result.sample_size == 5
    assert result.degrees_of_freedom == 4
    assert result.mean_difference > 0  # baseline consistently riskier than method
    assert result.t_statistic > 0
    assert 0.0 <= result.p_value <= 1.0


def test_paired_t_test_requires_matching_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        paired_t_test([1.0, 2.0], [1.0])


def test_paired_t_test_requires_at_least_two_pairs() -> None:
    with pytest.raises(ValueError, match="at least 2 paired observations"):
        paired_t_test([1.0], [2.0])


def test_paired_t_test_zero_variance_identical_values_is_not_significant() -> None:
    result = paired_t_test([1.0, 1.0, 1.0], [1.0, 1.0, 1.0])
    assert result.t_statistic == 0.0
    assert result.p_value == 1.0


def test_paired_t_test_zero_variance_nonzero_difference_is_maximally_significant() -> None:
    result = paired_t_test([2.0, 2.0, 2.0], [1.0, 1.0, 1.0])
    assert result.t_statistic == math.inf
    assert result.p_value == 0.0

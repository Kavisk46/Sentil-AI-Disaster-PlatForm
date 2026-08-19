"""The comparison metrics Milestone 10 requires: risk reduction, distance
overhead, and a real paired significance test.

**Statistical integrity**: `paired_t_test()` computes an actual Student's
t statistic and a real two-tailed p-value (via the regularized incomplete
beta function — a standard, exact relationship, not an approximation
dressed up as one; see its docstring). This repository never adds a
dependency lightly (see `research/pyproject.toml`), so this is a
from-scratch, stdlib-only implementation rather than pulling in scipy —
but it is a real test, not a placeholder. Nothing in this codebase may
claim statistical significance without calling this function (or an
equivalent real test) first.
"""

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass


def risk_reduction_percent(baseline_risk: float, method_risk: float) -> float | None:
    """`(baseline_risk - method_risk) / baseline_risk * 100`.

    `None` when `baseline_risk == 0.0` — reduction relative to zero risk
    is undefined (there is nothing to reduce), never silently reported as
    `0%` or `100%`. Callers (e.g. `research.core.report`) must handle
    `None` explicitly.
    """
    if baseline_risk == 0.0:
        return None
    return (baseline_risk - method_risk) / baseline_risk * 100.0


def distance_overhead_percent(baseline_distance: float, method_distance: float) -> float:
    """`(method_distance - baseline_distance) / baseline_distance * 100`.

    Raises `ValueError` for a non-positive `baseline_distance` — a
    same-origin/destination scenario has no meaningful distance-overhead
    baseline, so this is a genuinely degenerate input, not a case to
    silently paper over with `None` (contrast `risk_reduction_percent`,
    where a zero baseline is a real, expected outcome).
    """
    if baseline_distance <= 0.0:
        raise ValueError(
            "distance_overhead_percent requires a positive baseline_distance; got "
            f"{baseline_distance!r}."
        )
    return (method_distance - baseline_distance) / baseline_distance * 100.0


# ---------------------------------------------------------------------------
# Paired significance test (Student's t, two-tailed) — stdlib-only.
# ---------------------------------------------------------------------------


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    """Lentz's continued-fraction evaluation for the regularized
    incomplete beta function — the standard numerical recipe (Numerical
    Recipes §6.4), used because Python's stdlib has no incomplete-beta
    function of its own."""
    max_iterations = 200
    epsilon = 3e-14
    min_float = 1e-300

    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < min_float:
        d = min_float
    d = 1.0 / d
    h = d

    for m in range(1, max_iterations + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < min_float:
            d = min_float
        c = 1.0 + aa / c
        if abs(c) < min_float:
            c = min_float
        d = 1.0 / d
        h *= d * c

        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < min_float:
            d = min_float
        c = 1.0 + aa / c
        if abs(c) < min_float:
            c = min_float
        d = 1.0 / d
        delta = d * c
        h *= delta

        if abs(delta - 1.0) < epsilon:
            break

    return h


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """`I_x(a, b)` — the regularized incomplete beta function, for
    `0 <= x <= 1`, `a, b > 0`. Used by `student_t_two_tailed_p_value()`
    via the exact identity relating it to the Student's t CDF."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    log_beta = (
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log(1.0 - x)
    )
    front = math.exp(log_beta)

    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_continued_fraction(a, b, x) / a
    return 1.0 - front * _beta_continued_fraction(b, a, 1.0 - x) / b


def student_t_two_tailed_p_value(t_statistic: float, degrees_of_freedom: float) -> float:
    """Two-tailed p-value for Student's t distribution: the exact
    identity `P(|T| > |t|) = I_x(df/2, 1/2)` with `x = df / (df + t^2)`.
    `degrees_of_freedom` must be positive."""
    if degrees_of_freedom <= 0:
        raise ValueError(f"degrees_of_freedom must be positive; got {degrees_of_freedom!r}.")
    x = degrees_of_freedom / (degrees_of_freedom + t_statistic * t_statistic)
    return regularized_incomplete_beta(degrees_of_freedom / 2.0, 0.5, x)


@dataclass(frozen=True, slots=True)
class PairedTTestResult:
    """A real paired (dependent-samples) t-test result — `mean_difference`
    is `baseline - method` per pair, averaged."""

    mean_difference: float
    t_statistic: float
    degrees_of_freedom: int
    p_value: float
    sample_size: int


def paired_t_test(
    baseline_values: Sequence[float], method_values: Sequence[float]
) -> PairedTTestResult:
    """A paired, two-tailed Student's t-test on `baseline - method` for
    matched scenario pairs (e.g. risk-aware vs. shortest-path risk across
    N scenarios). Requires at least 2 paired observations — a t-test on a
    single pair has no defined variance.
    """
    if len(baseline_values) != len(method_values):
        raise ValueError(
            "baseline_values and method_values must be the same length (paired samples); got "
            f"{len(baseline_values)} and {len(method_values)}."
        )
    sample_size = len(baseline_values)
    if sample_size < 2:
        raise ValueError(
            f"paired_t_test requires at least 2 paired observations; got {sample_size}."
        )

    differences = [
        baseline - method for baseline, method in zip(baseline_values, method_values, strict=True)
    ]
    mean_difference = statistics.fmean(differences)
    stdev_difference = statistics.stdev(differences)
    degrees_of_freedom = sample_size - 1

    if stdev_difference == 0.0:
        # Every paired difference is identical — the t-statistic is
        # infinite (undefined) unless the differences are all zero, in
        # which case there is no effect and no reason to reject the null.
        if mean_difference == 0.0:
            t_statistic, p_value = 0.0, 1.0
        else:
            t_statistic, p_value = math.inf, 0.0
    else:
        standard_error = stdev_difference / math.sqrt(sample_size)
        t_statistic = mean_difference / standard_error
        p_value = student_t_two_tailed_p_value(t_statistic, degrees_of_freedom)

    return PairedTTestResult(
        mean_difference=mean_difference,
        t_statistic=t_statistic,
        degrees_of_freedom=degrees_of_freedom,
        p_value=p_value,
        sample_size=sample_size,
    )

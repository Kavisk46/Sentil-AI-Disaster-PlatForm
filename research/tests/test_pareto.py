import pytest

from research.core.pareto import ParetoPoint, describe_tradeoff, dominates, pareto_frontier


def test_dominates_requires_strictly_better_on_at_least_one_axis() -> None:
    a = ParetoPoint("a", distance_km=4.0, route_risk=0.3)
    b = ParetoPoint("b", distance_km=4.0, route_risk=0.3)
    assert not dominates(a, b)  # identical — neither dominates


def test_dominates_true_when_better_or_equal_everywhere_and_strictly_better_somewhere() -> None:
    better = ParetoPoint("better", distance_km=4.0, route_risk=0.2)
    worse = ParetoPoint("worse", distance_km=4.0, route_risk=0.3)
    assert dominates(better, worse)
    assert not dominates(worse, better)


def test_pareto_frontier_excludes_a_strictly_dominated_point() -> None:
    dominated = ParetoPoint("dominated", distance_km=5.0, route_risk=0.5)
    dominator = ParetoPoint("dominator", distance_km=4.0, route_risk=0.4)
    unrelated = ParetoPoint("unrelated", distance_km=3.0, route_risk=0.6)

    frontier = pareto_frontier([dominated, dominator, unrelated])

    assert dominated not in frontier
    assert dominator in frontier
    assert unrelated in frontier


def test_pareto_frontier_keeps_both_extremes_of_a_genuine_tradeoff() -> None:
    """Neither the lowest-risk nor the shortest-distance point should be
    assumed 'better' — both belong on the frontier when neither
    dominates the other."""
    lowest_risk = ParetoPoint("lowest_risk", distance_km=4.8, route_risk=0.31)
    shortest_distance = ParetoPoint("shortest_distance", distance_km=4.2, route_risk=0.81)

    frontier = pareto_frontier([lowest_risk, shortest_distance])

    assert lowest_risk in frontier
    assert shortest_distance in frontier


def test_describe_tradeoff_computes_real_percentages_never_hardcoded() -> None:
    lowest_risk = ParetoPoint("risk_aware", distance_km=4.8, route_risk=0.31)
    shortest_distance = ParetoPoint("shortest_path", distance_km=4.2, route_risk=0.81)

    summary = describe_tradeoff([lowest_risk, shortest_distance])

    assert summary.lowest_risk is lowest_risk
    assert summary.shortest_distance is shortest_distance
    assert summary.lowest_risk_distance_overhead_percent == pytest.approx(14.285714, rel=1e-6)
    assert summary.shortest_distance_risk_excess_percent == pytest.approx(161.290323, rel=1e-5)


def test_describe_tradeoff_handles_a_single_point_that_is_both_extremes() -> None:
    only = ParetoPoint("only", distance_km=1.0, route_risk=0.1)
    summary = describe_tradeoff([only])
    assert summary.lowest_risk is only
    assert summary.shortest_distance is only
    assert summary.lowest_risk_distance_overhead_percent == 0.0
    assert summary.shortest_distance_risk_excess_percent == 0.0


def test_describe_tradeoff_requires_at_least_one_point() -> None:
    with pytest.raises(ValueError, match="at least one point"):
        describe_tradeoff([])

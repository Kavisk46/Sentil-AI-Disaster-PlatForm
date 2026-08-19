import pytest

from research.core.experiment_figures import (
    configuration_comparison_figure,
    distance_overhead_figure,
    risk_reduction_figure,
    risk_vs_distance_figure,
)
from research.core.figures import BarValue, ScatterPoint, bar_chart_svg, scatter_svg
from research.core.reproducibility import build_reproducibility_metadata
from research.core.schemas import ExperimentResult


def _result(
    configuration: str,
    distance_km: float,
    route_risk: float,
    reduction: float | None,
    overhead: float | None,
) -> ExperimentResult:
    reproducibility = build_reproducibility_metadata(
        scenario_id="s1", dataset_version="d", model_version="n/a",
        routing_configuration={}, risk_configuration={},
    )
    return ExperimentResult(
        experiment_id=reproducibility.experiment_id,
        scenario_id="s1",
        configuration=configuration,
        distance_km=distance_km,
        route_risk=route_risk,
        risk_reduction_percent=reduction,
        distance_overhead_percent=overhead,
        runtime_ms=0.1,
        reproducibility=reproducibility,
    )


def test_scatter_svg_renders_one_circle_per_point() -> None:
    points = [ScatterPoint("a", 1.0, 0.5), ScatterPoint("b", 2.0, 0.2), ScatterPoint("c", 3.0, 0.8)]
    svg = scatter_svg(points, x_label="Distance", y_label="Risk", title="Test")
    assert svg.count("<circle") == 3
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")


def test_scatter_svg_requires_at_least_one_point() -> None:
    with pytest.raises(ValueError, match="at least one point"):
        scatter_svg([], x_label="x", y_label="y", title="t")


def test_bar_chart_svg_renders_one_rect_per_bar() -> None:
    bars = [BarValue("a", 10.0), BarValue("b", -5.0), BarValue("c", 0.0)]
    svg = bar_chart_svg(bars, y_label="Value", title="Test")
    assert svg.count("<rect") == 1 + 3  # background rect + one per bar


def test_bar_chart_svg_requires_at_least_one_bar() -> None:
    with pytest.raises(ValueError, match="at least one bar"):
        bar_chart_svg([], y_label="y", title="t")


def test_figures_escape_labels_that_look_like_markup() -> None:
    points = [ScatterPoint("<script>", 1.0, 1.0)]
    svg = scatter_svg(points, x_label="x", y_label="y", title="t")
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


def test_risk_vs_distance_figure_reflects_real_result_values() -> None:
    results = [
        _result("shortest_path", 4.2, 0.81, 0.0, 0.0),
        _result("risk_aware", 4.8, 0.31, 61.7, 14.3),
    ]
    svg = risk_vs_distance_figure(results)
    assert svg.count("<circle") == 2
    assert "shortest_path" in svg
    assert "risk_aware" in svg


def test_risk_reduction_figure_omits_results_with_no_defined_reduction() -> None:
    results = [
        _result("shortest_path", 4.2, 0.81, None, None),
        _result("risk_aware", 4.8, 0.31, 61.7, 14.3),
    ]
    svg = risk_reduction_figure(results)
    assert "risk_aware" in svg
    assert "61.7" in svg


def test_risk_reduction_figure_raises_when_nothing_is_defined() -> None:
    results = [_result("shortest_path", 4.2, 0.81, None, None)]
    with pytest.raises(ValueError, match="risk_reduction_percent"):
        risk_reduction_figure(results)


def test_distance_overhead_figure_raises_when_nothing_is_defined() -> None:
    results = [_result("shortest_path", 4.2, 0.81, None, None)]
    with pytest.raises(ValueError, match="distance_overhead_percent"):
        distance_overhead_figure(results)


def test_configuration_comparison_figure_includes_every_configuration() -> None:
    results = [
        _result("shortest_path", 4.2, 0.81, 0.0, 0.0),
        _result("risk_aware", 4.8, 0.31, 61.7, 14.3),
    ]
    svg = configuration_comparison_figure(results)
    assert svg.count("<rect") == 1 + 2
    assert "shortest_path" in svg and "risk_aware" in svg

"""The four figure types Milestone 10 asks for, built directly from
`ExperimentResult` records via the generic SVG primitives in
`research.core.figures`. No literal data values live in this module —
every number plotted is read from the `results` argument.
"""

from collections.abc import Sequence

from research.core.figures import BarValue, ScatterPoint, bar_chart_svg, scatter_svg
from research.core.schemas import ExperimentResult


def risk_vs_distance_figure(results: Sequence[ExperimentResult]) -> str:
    points = [
        ScatterPoint(label=result.configuration, x=result.distance_km, y=result.route_risk)
        for result in results
    ]
    return scatter_svg(
        points, x_label="Distance (km)", y_label="Route risk", title="Risk vs. distance"
    )


def risk_reduction_figure(results: Sequence[ExperimentResult]) -> str:
    bars = [
        BarValue(label=result.configuration, value=result.risk_reduction_percent)
        for result in results
        if result.risk_reduction_percent is not None
    ]
    if not bars:
        raise ValueError(
            "No results have a defined risk_reduction_percent (the baseline route may have "
            "had zero risk for every scenario given)."
        )
    return bar_chart_svg(bars, y_label="Risk reduction (%)", title="Risk reduction vs. baseline")


def distance_overhead_figure(results: Sequence[ExperimentResult]) -> str:
    bars = [
        BarValue(label=result.configuration, value=result.distance_overhead_percent)
        for result in results
        if result.distance_overhead_percent is not None
    ]
    if not bars:
        raise ValueError("No results have a defined distance_overhead_percent.")
    return bar_chart_svg(
        bars, y_label="Distance overhead (%)", title="Distance overhead vs. baseline"
    )


def configuration_comparison_figure(results: Sequence[ExperimentResult]) -> str:
    bars = [BarValue(label=result.configuration, value=result.route_risk) for result in results]
    return bar_chart_svg(bars, y_label="Route risk", title="Configuration comparison (route risk)")

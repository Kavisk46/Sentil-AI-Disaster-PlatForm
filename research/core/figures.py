"""Dependency-free SVG figure generation.

No matplotlib/plotly dependency: these are simple, correct scatter/bar
charts rendered as SVG markup directly from the caller's data — every
coordinate in the output is computed from a real input value, never a
hardcoded literal (aside from fixed layout constants like margins).
Deterministic: the same input always produces the same SVG string, which
`research/tests/test_figures.py` checks directly.
"""

from collections.abc import Sequence
from dataclasses import dataclass

_WIDTH = 640
_HEIGHT = 400
_MARGIN = 56
_BACKGROUND = "#0b1220"
_AXIS_COLOR = "#4b5563"
_TEXT_COLOR = "#e5e7eb"
_TITLE_COLOR = "#f3f4f6"
_MUTED_TEXT_COLOR = "#9ca3af"
_POINT_COLOR = "#38bdf8"
_POSITIVE_BAR_COLOR = "#34d399"
_NEGATIVE_BAR_COLOR = "#f87171"


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _svg_header(width: int = _WIDTH, height: int = _HEIGHT) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="sans-serif" font-size="11">'
        f'<rect width="{width}" height="{height}" fill="{_BACKGROUND}"/>'
    )


def _axis_line(x0: float, y0: float, x1: float, y1: float) -> str:
    return (
        f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
        f'stroke="{_AXIS_COLOR}" stroke-width="1"/>'
    )


def _title(text: str) -> str:
    return (
        f'<text x="{_WIDTH / 2:.1f}" y="24" fill="{_TITLE_COLOR}" text-anchor="middle" '
        f'font-size="14">{_escape(text)}</text>'
    )


def _axis_label(text: str, *, vertical: bool) -> str:
    if vertical:
        return (
            f'<text x="16" y="{_HEIGHT / 2:.1f}" fill="{_MUTED_TEXT_COLOR}" '
            f'transform="rotate(-90 16 {_HEIGHT / 2:.1f})" text-anchor="middle">'
            f"{_escape(text)}</text>"
        )
    return (
        f'<text x="{_WIDTH / 2:.1f}" y="{_HEIGHT - 16}" fill="{_MUTED_TEXT_COLOR}" '
        f'text-anchor="middle">{_escape(text)}</text>'
    )


@dataclass(frozen=True, slots=True)
class ScatterPoint:
    label: str
    x: float
    y: float


def scatter_svg(points: Sequence[ScatterPoint], *, x_label: str, y_label: str, title: str) -> str:
    """A distance-vs-risk (or similar) scatter plot — one labeled point
    per configuration/scenario."""
    if not points:
        raise ValueError("scatter_svg requires at least one point.")

    xs = [point.x for point in points]
    ys = [point.y for point in points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    x_range = (x_max - x_min) or 1.0
    y_range = (y_max - y_min) or 1.0

    def project_x(x: float) -> float:
        return _MARGIN + (x - x_min) / x_range * (_WIDTH - 2 * _MARGIN)

    def project_y(y: float) -> float:
        return _HEIGHT - _MARGIN - (y - y_min) / y_range * (_HEIGHT - 2 * _MARGIN)

    parts = [
        _svg_header(),
        _axis_line(_MARGIN, _HEIGHT - _MARGIN, _WIDTH - _MARGIN, _HEIGHT - _MARGIN),
        _axis_line(_MARGIN, _MARGIN, _MARGIN, _HEIGHT - _MARGIN),
    ]
    for point in points:
        cx, cy = project_x(point.x), project_y(point.y)
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="{_POINT_COLOR}"/>')
        parts.append(
            f'<text x="{cx + 8:.1f}" y="{cy - 8:.1f}" fill="{_TEXT_COLOR}">'
            f"{_escape(point.label)}</text>"
        )
    parts.append(_axis_label(x_label, vertical=False))
    parts.append(_axis_label(y_label, vertical=True))
    parts.append(_title(title))
    parts.append("</svg>")
    return "".join(parts)


@dataclass(frozen=True, slots=True)
class BarValue:
    label: str
    value: float


def bar_chart_svg(bars: Sequence[BarValue], *, y_label: str, title: str) -> str:
    """A labeled bar chart — positive values render upward in green,
    negative values downward in red (e.g. a risk *increase* under some
    configuration), so the sign is visible without relying on color
    alone (bar direction relative to the zero line is the non-color
    signal)."""
    if not bars:
        raise ValueError("bar_chart_svg requires at least one bar.")

    values = [bar.value for bar in bars]
    max_value = max(max(values), 0.0)
    min_value = min(min(values), 0.0)
    value_range = (max_value - min_value) or 1.0
    plot_height = _HEIGHT - 2 * _MARGIN
    plot_width = _WIDTH - 2 * _MARGIN
    slot_width = plot_width / len(bars)
    bar_width = slot_width * 0.6

    def project_y(value: float) -> float:
        return _HEIGHT - _MARGIN - (value - min_value) / value_range * plot_height

    zero_y = project_y(0.0)
    parts = [_svg_header(), _axis_line(_MARGIN, zero_y, _WIDTH - _MARGIN, zero_y)]

    for index, bar in enumerate(bars):
        x = _MARGIN + index * slot_width + (slot_width - bar_width) / 2
        bar_top = min(project_y(bar.value), zero_y)
        height = abs(project_y(bar.value) - zero_y)
        color = _POSITIVE_BAR_COLOR if bar.value >= 0 else _NEGATIVE_BAR_COLOR
        parts.append(
            f'<rect x="{x:.1f}" y="{bar_top:.1f}" width="{bar_width:.1f}" height="{height:.1f}" '
            f'fill="{color}"/>'
        )
        label_y = zero_y + 14 if bar.value >= 0 else zero_y - 6
        value_y = bar_top - 4 if bar.value >= 0 else bar_top + height + 12
        parts.append(
            f'<text x="{x + bar_width / 2:.1f}" y="{label_y:.1f}" fill="{_TEXT_COLOR}" '
            f'text-anchor="middle">{_escape(bar.label)}</text>'
        )
        parts.append(
            f'<text x="{x + bar_width / 2:.1f}" y="{value_y:.1f}" fill="{_TITLE_COLOR}" '
            f'text-anchor="middle">{bar.value:.1f}</text>'
        )

    parts.append(_axis_label(y_label, vertical=True))
    parts.append(_title(title))
    parts.append("</svg>")
    return "".join(parts)

"""Minimal SVG plotting, stdlib only.

INA-sim is offline-first with one dependency (PyYAML), so the reference figures
cannot pull in matplotlib or a JavaScript charting library. This is just enough
SVG to draw an honest scientific plot: linear and log axes, ticks with real
labels, polylines, shaded uncertainty bands, scatter points and a legend.

Deliberately small. If a figure needs more than this, the figure is too clever.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

Scale = Literal["linear", "log10"]

# Colour-blind safe qualitative palette (Okabe-Ito), which matters here because
# several figures encode material identity by colour alone.
PALETTE = [
    "#0072B2",  # blue
    "#D55E00",  # vermillion
    "#009E73",  # bluish green
    "#CC79A7",  # reddish purple
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
    "#8B4513",  # brown
    "#555555",  # grey
]

GRID = "#d8d8d8"
AXIS = "#333333"
TEXT = "#222222"
MUTED = "#666666"


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


@dataclass
class Series:
    """One line, optionally with a shaded band and/or scatter points."""

    label: str
    xs: Sequence[float]
    ys: Sequence[float]
    colour: str | None = None
    band_low: Sequence[float] | None = None
    band_high: Sequence[float] | None = None
    dashed: bool = False
    points_only: bool = False
    point_radius: float = 3.0


@dataclass
class Axis:
    label: str
    scale: Scale = "linear"
    lo: float | None = None
    hi: float | None = None
    ticks: list[float] | None = None
    invert: bool = False


@dataclass
class Figure:
    title: str
    x: Axis
    y: Axis
    series: list[Series] = field(default_factory=list)
    caption: str = ""
    width: int = 720
    height: int = 430
    margin_left: int = 78
    margin_right: int = 22
    margin_top: int = 40
    margin_bottom: int = 66
    annotations: list[tuple[float, float, str]] = field(default_factory=list)

    # -- scaling ---------------------------------------------------------

    def _transform(self, axis: Axis, value: float) -> float:
        if axis.scale == "log10":
            if value <= 0:
                return float("nan")
            return math.log10(value)
        return value

    def _bounds(self, axis: Axis, values: list[float]) -> tuple[float, float]:
        finite = [v for v in values if math.isfinite(v)]
        lo = self._transform(axis, axis.lo) if axis.lo is not None else min(finite)
        hi = self._transform(axis, axis.hi) if axis.hi is not None else max(finite)
        if lo == hi:
            lo, hi = lo - 0.5, hi + 0.5
        pad = (hi - lo) * 0.04
        return lo - pad, hi + pad

    def _collect(self) -> tuple[tuple[float, float], tuple[float, float]]:
        xs: list[float] = []
        ys: list[float] = []
        for s in self.series:
            xs.extend(self._transform(self.x, v) for v in s.xs)
            ys.extend(self._transform(self.y, v) for v in s.ys)
            for band in (s.band_low, s.band_high):
                if band:
                    ys.extend(self._transform(self.y, v) for v in band)
        if not xs:
            xs, ys = [0.0, 1.0], [0.0, 1.0]
        return self._bounds(self.x, xs), self._bounds(self.y, ys)

    # -- rendering -------------------------------------------------------

    def render(self) -> str:
        (x_lo, x_hi), (y_lo, y_hi) = self._collect()
        plot_w = self.width - self.margin_left - self.margin_right
        plot_h = self.height - self.margin_top - self.margin_bottom

        def px(value: float) -> float:
            t = (self._transform(self.x, value) - x_lo) / (x_hi - x_lo)
            if self.x.invert:
                t = 1.0 - t
            return self.margin_left + t * plot_w

        def py(value: float) -> float:
            t = (self._transform(self.y, value) - y_lo) / (y_hi - y_lo)
            return self.margin_top + (1.0 - t) * plot_h

        parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} '
            f'{self.height}" width="100%" role="img" '
            f'aria-label="{_esc(self.title)}">',
            f'<rect x="0" y="0" width="{self.width}" height="{self.height}" '
            'fill="#ffffff"/>',
            f'<text x="{self.margin_left}" y="24" font-size="15" '
            f'font-family="Georgia, serif" fill="{TEXT}">{_esc(self.title)}</text>',
        ]

        x_ticks = self.x.ticks or _nice_ticks(x_lo, x_hi, self.x.scale)
        y_ticks = self.y.ticks or _nice_ticks(y_lo, y_hi, self.y.scale)

        for tick in y_ticks:
            value = 10**tick if self.y.scale == "log10" else tick
            y = py(value)
            if not (self.margin_top - 1 <= y <= self.margin_top + plot_h + 1):
                continue
            parts.append(
                f'<line x1="{self.margin_left}" y1="{y:.1f}" '
                f'x2="{self.margin_left + plot_w}" y2="{y:.1f}" '
                f'stroke="{GRID}" stroke-width="1"/>'
            )
            parts.append(
                f'<text x="{self.margin_left - 8}" y="{y + 4:.1f}" font-size="11" '
                f'text-anchor="end" font-family="monospace" fill="{MUTED}">'
                f"{_fmt_tick(tick, self.y.scale)}</text>"
            )

        for tick in x_ticks:
            value = 10**tick if self.x.scale == "log10" else tick
            x = px(value)
            if not (self.margin_left - 1 <= x <= self.margin_left + plot_w + 1):
                continue
            parts.append(
                f'<line x1="{x:.1f}" y1="{self.margin_top}" x2="{x:.1f}" '
                f'y2="{self.margin_top + plot_h}" stroke="{GRID}" stroke-width="1"/>'
            )
            parts.append(
                f'<text x="{x:.1f}" y="{self.margin_top + plot_h + 18}" '
                f'font-size="11" text-anchor="middle" font-family="monospace" '
                f'fill="{MUTED}">{_fmt_tick(tick, self.x.scale)}</text>'
            )

        parts.append(
            f'<rect x="{self.margin_left}" y="{self.margin_top}" width="{plot_w}" '
            f'height="{plot_h}" fill="none" stroke="{AXIS}" stroke-width="1"/>'
        )

        for i, s in enumerate(self.series):
            colour = s.colour or PALETTE[i % len(PALETTE)]
            if s.band_low and s.band_high:
                pts_up = [
                    (px(x), py(v))
                    for x, v in zip(s.xs, s.band_high)
                    if math.isfinite(py(v))
                ]
                pts_dn = [
                    (px(x), py(v))
                    for x, v in reversed(list(zip(s.xs, s.band_low)))
                    if math.isfinite(py(v))
                ]
                if pts_up and pts_dn:
                    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts_up + pts_dn)
                    parts.append(
                        f'<polygon points="{path}" fill="{colour}" '
                        'fill-opacity="0.13" stroke="none"/>'
                    )
            if s.points_only:
                for x, y in zip(s.xs, s.ys):
                    cx, cy = px(x), py(y)
                    if math.isfinite(cx) and math.isfinite(cy):
                        parts.append(
                            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" '
                            f'r="{s.point_radius}" fill="{colour}" '
                            'fill-opacity="0.75" stroke="#ffffff" stroke-width="0.7"/>'
                        )
            else:
                pts = [
                    f"{px(x):.1f},{py(y):.1f}"
                    for x, y in zip(s.xs, s.ys)
                    if math.isfinite(px(x)) and math.isfinite(py(y))
                ]
                if pts:
                    dash = ' stroke-dasharray="6 4"' if s.dashed else ""
                    parts.append(
                        f'<polyline points="{" ".join(pts)}" fill="none" '
                        f'stroke="{colour}" stroke-width="2.1" '
                        f'stroke-linejoin="round"{dash}/>'
                    )

        for x_val, y_val, text in self.annotations:
            parts.append(
                f'<text x="{px(x_val):.1f}" y="{py(y_val):.1f}" font-size="11" '
                f'font-family="Georgia, serif" fill="{MUTED}">{_esc(text)}</text>'
            )

        parts.append(
            f'<text x="{self.margin_left + plot_w / 2:.0f}" '
            f'y="{self.height - 26}" font-size="12" text-anchor="middle" '
            f'font-family="Georgia, serif" fill="{TEXT}">{_esc(self.x.label)}</text>'
        )
        cy = self.margin_top + plot_h / 2
        parts.append(
            f'<text x="18" y="{cy:.0f}" font-size="12" text-anchor="middle" '
            f'font-family="Georgia, serif" fill="{TEXT}" '
            f'transform="rotate(-90 18 {cy:.0f})">{_esc(self.y.label)}</text>'
        )

        parts.append(self._legend(plot_w))
        parts.append("</svg>")
        return "\n".join(parts)

    def _legend(self, plot_w: int) -> str:
        labelled = [s for s in self.series if s.label]
        if not labelled:
            return ""
        out = []
        x = self.margin_left
        y = self.height - 8
        for i, s in enumerate(self.series):
            if not s.label:
                continue
            colour = s.colour or PALETTE[i % len(PALETTE)]
            if s.points_only:
                # Scatter series get a dot, so the key matches the mark.
                out.append(
                    f'<circle cx="{x + 8}" cy="{y - 4}" r="3.4" fill="{colour}" '
                    'fill-opacity="0.75" stroke="#ffffff" stroke-width="0.7"/>'
                )
            else:
                out.append(
                    f'<line x1="{x}" y1="{y - 4}" x2="{x + 16}" y2="{y - 4}" '
                    f'stroke="{colour}" stroke-width="2.6"'
                    + (' stroke-dasharray="5 3"' if s.dashed else "")
                    + "/>"
                )
            out.append(
                f'<text x="{x + 21}" y="{y}" font-size="11" '
                f'font-family="monospace" fill="{TEXT}">{_esc(s.label)}</text>'
            )
            x += 26 + int(7.0 * len(s.label))
            if x > self.margin_left + plot_w - 60:
                x = self.margin_left
                y += 15
        return "\n".join(out)


def _fmt_tick(value: float, scale: Scale) -> str:
    if scale == "log10":
        return f"1e{int(round(value))}"
    if abs(value) >= 1000 or (value != 0 and abs(value) < 0.01):
        return f"{value:.0e}"
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value))}"
    return f"{value:g}"


def _nice_ticks(lo: float, hi: float, scale: Scale) -> list[float]:
    if scale == "log10":
        start, end = math.floor(lo), math.ceil(hi)
        step = max(1, int((end - start) // 8) + 1)
        return [float(v) for v in range(int(start), int(end) + 1, step)]
    span = hi - lo
    if span <= 0:
        return [lo]
    raw = span / 6.0
    magnitude = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 2.5, 5, 10):
        step = mult * magnitude
        if raw <= step:
            break
    first = math.ceil(lo / step) * step
    ticks: list[float] = []
    value = first
    while value <= hi + 1e-9:
        ticks.append(round(value, 10))
        value += step
    return ticks


def figure_block(fig: Figure, sources: str = "") -> dict[str, Any]:
    """Figure plus its caption, ready for the HTML page."""
    return {
        "title": fig.title,
        "svg": fig.render(),
        "caption": fig.caption,
        "sources": sources,
    }

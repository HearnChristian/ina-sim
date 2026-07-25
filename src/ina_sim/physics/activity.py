"""Literature-informed relative activity vs temperature (table lookup).

Directional teaching calibration — NOT measured ice-nucleating particle
concentrations ns(T). Missing agents fall back to legacy exp falloff.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import Any

import yaml


@lru_cache(maxsize=1)
def _load_curves() -> dict[str, Any]:
    ref = resources.files("ina_sim.library").joinpath("activity_curves.yaml")
    with ref.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def activity_citation(agent_id: str) -> str | None:
    data = _load_curves()
    curve = (data.get("curves") or {}).get(agent_id)
    if not curve:
        return None
    return curve.get("citation")


def uncertainty_fraction(confidence: str) -> float:
    data = _load_curves()
    u = data.get("uncertainty") or {}
    return float(u.get(confidence, u.get("medium", 0.25)))


def table_activity(agent_id: str, temp_c: float) -> float | None:
    """Linear interpolation on activity table; None if no curve."""
    data = _load_curves()
    curve = (data.get("curves") or {}).get(agent_id)
    if not curve:
        return None
    points = curve.get("points") or []
    if not points:
        return None
    pts = sorted((float(t), float(a)) for t, a in points)
    # pts sorted by T ascending (cold to warm or reverse — sort by T)
    if temp_c <= pts[0][0]:
        return max(0.0, min(1.0, pts[0][1]))
    if temp_c >= pts[-1][0]:
        return max(0.0, min(1.0, pts[-1][1]))
    for i in range(len(pts) - 1):
        t0, a0 = pts[i]
        t1, a1 = pts[i + 1]
        if t0 <= temp_c <= t1:
            if t1 == t0:
                return a0
            w = (temp_c - t0) / (t1 - t0)
            return max(0.0, min(1.0, a0 + w * (a1 - a0)))
    return pts[-1][1]


def temp_activity_factor(
    agent_id: str,
    temp_c: float,
    optimal_temp_c: float,
    width_c: float = 10.0,
) -> tuple[float, str]:
    """Return (factor 0–1, method: 'table'|'legacy_exp')."""
    tab = table_activity(agent_id, temp_c)
    if tab is not None:
        return tab, "table"
    import math

    if width_c <= 0:
        return 0.0, "legacy_exp"
    val = math.exp(-abs(temp_c - optimal_temp_c) / width_c)
    return (val if math.isfinite(val) else 0.0), "legacy_exp"

"""Finite-value guards and physical range clamps shared by physics modules."""

from __future__ import annotations

import math
from typing import Any


# Operating envelope for this learning lab (not global climate extremes)
T_MIN_C = -80.0
T_MAX_C = 40.0
RH_MIN = 0.0
RH_MAX = 100.0
P_MIN_HPA = 50.0
P_MAX_HPA = 1100.0
VOLUME_MIN_M3 = 1e-6
VOLUME_MAX_M3 = 1e12
DENSITY_MAX_PER_L = 1e7
DIAMETER_MIN_UM = 1e-3
DIAMETER_MAX_UM = 100.0


def is_finite_number(x: Any) -> bool:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v)


def require_finite(name: str, x: float) -> float:
    if not is_finite_number(x):
        raise ValueError(f"{name} must be a finite number, got {x!r}")
    return float(x)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def clamp_temperature_c(temp_c: float, *, strict: bool = False) -> float:
    t = require_finite("temperature_c", temp_c)
    if t <= -273.15:
        raise ValueError("temperature_c must be above absolute zero")
    if strict and not (T_MIN_C <= t <= T_MAX_C):
        raise ValueError(f"temperature_c outside lab envelope [{T_MIN_C}, {T_MAX_C}] °C")
    return clamp(t, T_MIN_C, T_MAX_C) if not strict else t


def clamp_rh(rh: float) -> float:
    return clamp(require_finite("relative_humidity_pct", rh), RH_MIN, RH_MAX)


def clamp_pressure_hpa(p: float, *, strict: bool = False) -> float:
    p = require_finite("pressure_hpa", p)
    if p <= 0:
        raise ValueError("pressure_hpa must be positive")
    if strict and not (P_MIN_HPA <= p <= P_MAX_HPA):
        raise ValueError(f"pressure_hpa outside lab envelope [{P_MIN_HPA}, {P_MAX_HPA}]")
    return clamp(p, P_MIN_HPA, P_MAX_HPA) if not strict else p


def safe_div(num: float, den: float, default: float = 0.0) -> float:
    if not is_finite_number(num) or not is_finite_number(den) or den == 0.0:
        return default
    out = num / den
    return out if math.isfinite(out) else default

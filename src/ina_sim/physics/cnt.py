"""Classical nucleation theory (CNT) educational estimates.

These are *order-of-magnitude teaching numbers*, not operational nucleation rates.
Used to expose free-energy barriers, critical radii, and heterogeneous reduction
factors so rankings can carry a CNT-informed secondary score.

References (conceptual):
  ΔG* = (16π/3) σ³ v_m² / (kT ln S)²     homogeneous free-energy barrier
  r*  = 2 σ v_m / (kT ln S)              critical cluster radius
  f(m) = heterogeneous factor from contact-angle cosine m
  J   ~ J0 exp(−ΔG*/kT)                  rate (we report log10-friendly scale)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ina_sim.physics.validate import clamp_temperature_c, is_finite_number, require_finite

# Physical constants
K_B = 1.380649e-23  # J/K
# Ice–water interfacial energy proxy (J/m²) — literature spans ~0.02–0.033
SIGMA_ICE_WATER = 0.028
# Molecular volume of ice (m³/molecule) ~ 3.2e-29
V_M_ICE = 3.2e-29
# Pre-factor placeholder for educational rate scale (m^-3 s^-1)
J0_HOMO = 1e38


@dataclass(frozen=True)
class CNTResult:
    """Homogeneous / heterogeneous CNT snapshot at one (T, S)."""

    temperature_c: float
    supersaturation: float
    delta_g_star_j: float | None
    delta_g_star_kt: float | None
    r_star_m: float | None
    r_star_nm: float | None
    f_hetero: float
    delta_g_hetero_kt: float | None
    log10_j_homo: float | None
    log10_j_hetero: float | None
    valid: bool
    note: str

    def as_dict(self) -> dict:
        return {
            "temperature_c": self.temperature_c,
            "supersaturation": round(self.supersaturation, 4) if is_finite_number(self.supersaturation) else None,
            "delta_g_star_kt": (
                None if self.delta_g_star_kt is None else round(self.delta_g_star_kt, 2)
            ),
            "r_star_nm": None if self.r_star_nm is None else round(self.r_star_nm, 3),
            "f_hetero": round(self.f_hetero, 4),
            "delta_g_hetero_kt": (
                None
                if self.delta_g_hetero_kt is None
                else round(self.delta_g_hetero_kt, 2)
            ),
            "log10_j_homo": (
                None if self.log10_j_homo is None else round(self.log10_j_homo, 2)
            ),
            "log10_j_hetero": (
                None if self.log10_j_hetero is None else round(self.log10_j_hetero, 2)
            ),
            "valid": self.valid,
            "note": self.note,
        }


def contact_parameter_from_lattice(lattice_match: float | None) -> float:
    """Map lattice-match score (0–1) → contact-angle cosine m ∈ [−1, 1].

    Higher lattice match → m closer to 1 → stronger wetting / lower barrier.
    """
    if lattice_match is None or not is_finite_number(lattice_match):
        return 0.3  # modest default
    x = max(0.0, min(1.0, float(lattice_match)))
    return 0.95 * x


def heterogeneous_factor(m: float) -> float:
    """Classic CNT geometric factor f(m) for a spherical cap on a flat substrate.

    f(m) = (2 + m)(1 − m)² / 4
    f → 0 as m → 1 (perfect match); f → 1 as m → −1.
    """
    if not is_finite_number(m):
        m = 0.0
    m = max(-1.0, min(1.0, float(m)))
    f = ((2.0 + m) * (1.0 - m) ** 2) / 4.0
    return max(0.0, min(1.0, f))


def homogeneous_barrier(
    temp_c: float,
    supersaturation: float,
    sigma: float = SIGMA_ICE_WATER,
    v_m: float = V_M_ICE,
) -> tuple[float | None, float | None, float | None]:
    """Return (ΔG* [J], ΔG*/kT, r* [m]) or Nones if S ≤ 1 or invalid."""
    if not is_finite_number(supersaturation) or supersaturation <= 1.0 + 1e-9:
        return None, None, None
    if not is_finite_number(sigma) or sigma <= 0:
        return None, None, None
    if not is_finite_number(v_m) or v_m <= 0:
        return None, None, None
    t = clamp_temperature_c(temp_c)
    t_k = t + 273.15
    if t_k <= 1e-6:
        return None, None, None
    try:
        ln_s = math.log(supersaturation)
    except ValueError:
        return None, None, None
    if ln_s <= 0:
        return None, None, None
    kt = K_B * t_k
    denom = 3.0 * (kt * ln_s) ** 2
    if denom <= 0:
        return None, None, None
    dg = (16.0 * math.pi * sigma**3 * v_m**2) / denom
    r_star = (2.0 * sigma * v_m) / (kt * ln_s)
    if not (math.isfinite(dg) and math.isfinite(r_star) and dg > 0 and r_star > 0):
        return None, None, None
    return dg, dg / kt, r_star


def log10_nucleation_rate(delta_g_over_kt: float | None, j0: float = J0_HOMO) -> float | None:
    """Educational log10(J) from barrier; clamps extreme values."""
    if delta_g_over_kt is None or not is_finite_number(delta_g_over_kt):
        return None
    if not is_finite_number(j0) or j0 <= 0:
        return None
    val = math.log10(j0) - float(delta_g_over_kt) / math.log(10.0)
    if not math.isfinite(val):
        return None
    return max(-50.0, min(50.0, val))


def cnt_estimate(
    temp_c: float,
    supersaturation: float,
    lattice_match: float | None = None,
    contact_m: float | None = None,
) -> CNTResult:
    """Homogeneous + heterogeneous CNT snapshot."""
    try:
        t = clamp_temperature_c(temp_c)
        s = require_finite("supersaturation", supersaturation)
    except ValueError as e:
        return CNTResult(
            temperature_c=temp_c if is_finite_number(temp_c) else 0.0,
            supersaturation=0.0,
            delta_g_star_j=None,
            delta_g_star_kt=None,
            r_star_m=None,
            r_star_nm=None,
            f_hetero=1.0,
            delta_g_hetero_kt=None,
            log10_j_homo=None,
            log10_j_hetero=None,
            valid=False,
            note=str(e),
        )

    if contact_m is not None and is_finite_number(contact_m):
        m = float(contact_m)
    else:
        m = contact_parameter_from_lattice(lattice_match)
    f = heterogeneous_factor(m)
    dg, dg_kt, r_star = homogeneous_barrier(t, s)

    if dg is None:
        return CNTResult(
            temperature_c=t,
            supersaturation=s,
            delta_g_star_j=None,
            delta_g_star_kt=None,
            r_star_m=None,
            r_star_nm=None,
            f_hetero=f,
            delta_g_hetero_kt=None,
            log10_j_homo=None,
            log10_j_hetero=None,
            valid=False,
            note="S≤1: classical barrier undefined (no supersaturation driving force)",
        )

    dg_het_kt = dg_kt * f if dg_kt is not None else None
    return CNTResult(
        temperature_c=t,
        supersaturation=s,
        delta_g_star_j=dg,
        delta_g_star_kt=dg_kt,
        r_star_m=r_star,
        r_star_nm=(r_star * 1e9) if r_star is not None else None,
        f_hetero=f,
        delta_g_hetero_kt=dg_het_kt,
        log10_j_homo=log10_nucleation_rate(dg_kt),
        log10_j_hetero=log10_nucleation_rate(dg_het_kt),
        valid=True,
        note="Educational CNT — not lab-calibrated rates",
    )


def cnt_activity_score(
    temp_c: float,
    supersaturation: float,
    lattice_match: float | None,
    *,
    floor: float = 1e-6,
) -> float:
    """Map heterogeneous CNT rate to a 0–1 score for secondary ranking.

    When S≤1 (common for immersion w.r.t liquid), use a temperature-activated
    proxy: colder → higher activity, modulated by f(m).
    """
    floor = max(0.0, min(1.0, floor))
    try:
        t = clamp_temperature_c(temp_c)
        s = float(supersaturation) if is_finite_number(supersaturation) else 1.0
    except ValueError:
        return floor

    m = contact_parameter_from_lattice(lattice_match)
    f = heterogeneous_factor(m)
    if s > 1.0:
        est = cnt_estimate(t, s, contact_m=m)
        if est.log10_j_hetero is None:
            return floor
        return max(floor, min(1.0, (est.log10_j_hetero + 20.0) / 40.0))

    supercool = max(0.0, -t)
    logistic = 1.0 / (1.0 + math.exp(-(supercool - 15.0) / 5.0))
    wetting = max(0.0, 1.0 - f)
    score = 0.15 + 0.85 * logistic * (0.3 + 0.7 * wetting)
    if not math.isfinite(score):
        return floor
    return max(floor, min(1.0, score))

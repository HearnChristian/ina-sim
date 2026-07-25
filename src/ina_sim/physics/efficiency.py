"""Agent efficiency / relative score model (empirical-first).

Design intent (v0.2.1 rigor pass):
- For ice-track agents with activity tables, the **score is 0–1 relative to AgI peak**:
    score = peak_strength × a(T) × mode_factor × density_factor
  where a(T) ∈ [0,1] is the literature-shaped activity curve (peak 1 at T_opt-ish)
  and peak_strength is agent peak effectiveness vs AgI (AgI = 1.0).
- Class/logistic stacking that crushed AgI to ~0.69 at −10 °C is **removed** for
  table agents so T-dependence is readable and comparable on a fixed [0,1] axis.
- CNT remains a **secondary diagnostic**, not a silent multiplier of the main score
  (optional 2% blend max for ice nucleants — does not dominate).
- Warm-cloud track still isolates CCN/hygroscopic ranking.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ina_sim.models.candidate import Candidate
from ina_sim.models.conditions import Conditions
from ina_sim.physics.activity import activity_citation, temp_activity_factor
from ina_sim.physics.atmosphere import supersaturation_ice, supersaturation_water
from ina_sim.physics.cnt import cnt_activity_score


@dataclass(frozen=True)
class EfficiencyBreakdown:
    overall: float
    temp_factor: float
    density_factor: float
    supersaturation_factor: float
    mode_factor: float
    class_factor: float
    cnt_score: float
    rating: str
    pathway: str
    temp_method: str  # table | legacy_exp
    citation: str | None = None
    score_model: str = "peak_x_activity"  # documentation of formula family


def temp_efficiency_factor(temp_c: float, optimal_temp_c: float, width_c: float = 10.0) -> float:
    if width_c <= 0 or not math.isfinite(temp_c) or not math.isfinite(optimal_temp_c):
        return 0.0
    val = math.exp(-abs(temp_c - optimal_temp_c) / width_c)
    return val if math.isfinite(val) else 0.0


def density_efficiency_factor(seeding_density_per_l: float, half_sat_per_l: float = 50.0) -> float:
    if half_sat_per_l <= 0:
        return 1.0
    if not math.isfinite(seeding_density_per_l) or seeding_density_per_l < 0:
        return 0.0
    return min(1.0, seeding_density_per_l / half_sat_per_l)


def supersaturation_factor_legacy(relative_humidity_pct: float, threshold: float = 80.0) -> float:
    if not math.isfinite(relative_humidity_pct):
        return 0.0
    return max(0.0, (relative_humidity_pct - threshold) / 20.0)


def mode_factor(mode: str, agent_class: str, s_ice: float, temp_c: float) -> float:
    mode = (mode or "immersion").lower()
    if mode == "immersion":
        if agent_class == "ice_nucleant":
            return 1.0 if temp_c < 0 else 0.12
        if agent_class == "hygroscopic":
            return 0.9
        return 0.7
    if mode == "deposition":
        if s_ice <= 1.0:
            return 0.05
        ramp = min(1.0, (s_ice - 1.0) / 0.3)
        if agent_class == "ice_nucleant":
            return 0.25 + 0.75 * ramp
        if agent_class == "hygroscopic":
            return 0.1 + 0.25 * ramp
        return 0.12 * ramp
    if mode == "contact":
        if agent_class == "ice_nucleant":
            return 0.8 if temp_c < -5 else 0.35
        return 0.4
    return 0.5


def class_pathway_factor(
    agent_class: str,
    temp_c: float,
    s_water: float,
    *,
    track: str = "ice",
    table_driven: bool = False,
) -> tuple[float, str]:
    track = (track or "ice").lower()

    if track == "warm_cloud":
        if agent_class == "hygroscopic":
            warm = 1.0 / (1.0 + math.exp(-(temp_c + 2.0) / 4.0))
            wet = max(0.2, min(1.0, s_water))
            return 0.55 + 0.45 * warm * wet, "hygroscopic_ccn"
        if agent_class == "control":
            return 0.05, "control"
        if agent_class == "ice_nucleant":
            return 0.10, "ice_nucleation_off_track"
        if agent_class == "organic":
            return 0.30, "organic"
        return 0.2, "unknown"

    # Ice track
    if agent_class == "control":
        return 1.0, "control"  # strength already tiny in base / table
    if agent_class == "organic":
        return 0.85, "organic"
    if agent_class == "hygroscopic":
        # Low ice activity; table agents use a(T) as primary
        warm = 1.0 / (1.0 + math.exp(-(temp_c + 5.0) / 4.0))
        wet = max(0.2, min(1.0, s_water))
        return 0.35 + 0.25 * warm * wet, "hygroscopic_ccn"
    if agent_class == "ice_nucleant":
        # Table-driven: do not re-apply a second T logistic (double counting)
        if table_driven:
            return 1.0, "ice_nucleation"
        cold = 1.0 / (1.0 + math.exp((temp_c + 8.0) / 4.0))
        return 0.55 + 0.45 * cold, "ice_nucleation"
    return 0.5, "unknown"


def rating_from_efficiency(overall: float) -> str:
    if overall > 0.7:
        return "high"
    if overall > 0.4:
        return "medium"
    return "low"


def agent_efficiency(candidate: Candidate, conditions: Conditions) -> EfficiencyBreakdown:
    t_fac, t_method = temp_activity_factor(
        candidate.id,
        conditions.temperature_c,
        candidate.optimal_temp_c,
    )
    d_fac = density_efficiency_factor(conditions.seeding_density_per_l)
    s_fac = supersaturation_factor_legacy(conditions.relative_humidity_pct)
    s_w = supersaturation_water(conditions.temperature_c, conditions.relative_humidity_pct)
    s_i = supersaturation_ice(conditions.temperature_c, conditions.relative_humidity_pct)
    track = getattr(conditions, "track", "ice") or "ice"
    table_driven = t_method == "table"

    # peak_strength: for table agents this is "peak vs AgI" (AgI=1). Stored as base_efficiency.
    peak = max(0.0, min(1.0, candidate.base_efficiency))
    # Lattice match: only gentle nudge for non-table ice nucleants; table already encodes T shape
    lattice = candidate.lattice_match_score
    if (
        not table_driven
        and lattice is not None
        and candidate.agent_class.value == "ice_nucleant"
    ):
        peak = min(1.0, peak * (0.75 + 0.25 * max(0.0, min(1.0, lattice))))

    m_fac = mode_factor(
        conditions.mode,
        candidate.agent_class.value,
        s_i,
        conditions.temperature_c,
    )
    c_fac, pathway = class_pathway_factor(
        candidate.agent_class.value,
        conditions.temperature_c,
        s_w,
        track=track,
        table_driven=table_driven and candidate.agent_class.value == "ice_nucleant",
    )

    if conditions.mode == "deposition":
        cnt_s = s_i
    else:
        cnt_s = 1.0
    cnt = cnt_activity_score(
        conditions.temperature_c,
        cnt_s,
        lattice if candidate.agent_class.value == "ice_nucleant" else None,
    )
    if candidate.agent_class.value == "control":
        cnt = min(cnt, 0.05)
    if candidate.agent_class.value == "hygroscopic":
        cnt *= 0.35

    # Primary score on [0, 1]: peak × activity(T) × mode × class
    overall = peak * t_fac * m_fac * c_fac
    # Tiny CNT diagnostic blend (≤2%) — then loading multiplies so zero density ⇒ zero score
    if track == "ice" and candidate.agent_class.value == "ice_nucleant":
        overall = 0.98 * overall + 0.02 * cnt
    overall *= d_fac
    if not math.isfinite(overall):
        overall = 0.0
    overall = max(0.0, min(1.0, overall))

    return EfficiencyBreakdown(
        overall=overall,
        temp_factor=t_fac,
        density_factor=d_fac,
        supersaturation_factor=s_fac,
        mode_factor=m_fac,
        class_factor=c_fac,
        cnt_score=cnt,
        rating=rating_from_efficiency(overall),
        pathway=pathway,
        temp_method=t_method,
        citation=activity_citation(candidate.id) or candidate.source,
        score_model="peak_x_aT_x_mode_x_load",
    )


def condensable_water_kg(
    total_vapor_kg: float,
    efficiency: EfficiencyBreakdown,
) -> float:
    if not math.isfinite(total_vapor_kg) or total_vapor_kg < 0:
        return 0.0
    out = total_vapor_kg * efficiency.supersaturation_factor * efficiency.overall
    return out if math.isfinite(out) and out >= 0 else 0.0

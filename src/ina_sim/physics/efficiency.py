"""Agent efficiency heuristics ported/extended from supercool-water-calculator.

Legacy JS:
    tempEfficiencyFactor = exp(-|T - optimalT| / 10)
    densityEfficiencyFactor = min(1, seedingDensity / 50)
    overallEfficiency = base_efficiency * tempFactor * densityFactor

IMPORTANT:
- This is a *learning/demo* efficiency proxy, not CNT or MD.
- Hygroscopic agents (NaCl, CaCl2) and ice nucleants (AgI, feldspar) are
  different physical mechanisms; they share this interface only for ranking UX.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ina_sim.models.candidate import Candidate
from ina_sim.models.conditions import Conditions


@dataclass(frozen=True)
class EfficiencyBreakdown:
    overall: float
    temp_factor: float
    density_factor: float
    supersaturation_factor: float
    rating: str


def temp_efficiency_factor(temp_c: float, optimal_temp_c: float, width_c: float = 10.0) -> float:
    """Gaussian-ish falloff around agent optimal temperature (legacy exp form)."""
    return math.exp(-abs(temp_c - optimal_temp_c) / width_c)


def density_efficiency_factor(seeding_density_per_l: float, half_sat_per_l: float = 50.0) -> float:
    """Saturating response to particle loading (legacy min(1, n/50))."""
    if half_sat_per_l <= 0:
        return 1.0
    return min(1.0, seeding_density_per_l / half_sat_per_l)


def supersaturation_factor(relative_humidity_pct: float, threshold: float = 80.0) -> float:
    """Legacy: max(0, (RH - 80) / 20). Used only for condensable-water estimate."""
    return max(0.0, (relative_humidity_pct - threshold) / 20.0)


def rating_from_efficiency(overall: float) -> str:
    if overall > 0.7:
        return "high"
    if overall > 0.4:
        return "medium"
    return "low"


def agent_efficiency(candidate: Candidate, conditions: Conditions) -> EfficiencyBreakdown:
    """Combine base agent efficiency with environmental factors."""
    t_fac = temp_efficiency_factor(conditions.temperature_c, candidate.optimal_temp_c)
    d_fac = density_efficiency_factor(conditions.seeding_density_per_l)
    s_fac = supersaturation_factor(conditions.relative_humidity_pct)
    base = max(0.0, min(1.0, candidate.base_efficiency))
    # Lattice match (if present) gently boosts ice nucleants only
    lattice = candidate.lattice_match_score
    if lattice is not None and candidate.agent_class.value == "ice_nucleant":
        base = min(1.0, base * (0.7 + 0.3 * max(0.0, min(1.0, lattice))))
    overall = base * t_fac * d_fac
    return EfficiencyBreakdown(
        overall=overall,
        temp_factor=t_fac,
        density_factor=d_fac,
        supersaturation_factor=s_fac,
        rating=rating_from_efficiency(overall),
    )


def condensable_water_kg(
    total_vapor_kg: float,
    efficiency: EfficiencyBreakdown,
) -> float:
    """Legacy: totalWaterVapor * supersaturationFactor * overallEfficiency."""
    return total_vapor_kg * efficiency.supersaturation_factor * efficiency.overall

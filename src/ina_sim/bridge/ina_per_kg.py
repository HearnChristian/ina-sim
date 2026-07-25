"""Particle/bulk bridge: activity → engineering INA/kg proxy + relative score.

Relative score is now **already on a 0–1 AgI-peak scale** when produced by the
efficiency model (`peak × a(T) × …`). `relative_ina_score` therefore defaults
to identity (no divide-by-0.85 crush).
"""

from __future__ import annotations

from dataclasses import dataclass

from ina_sim.models.candidate import Candidate


@dataclass(frozen=True)
class ParticleAssumptions:
    diameter_um: float = 1.0
    active_site_fraction: float = 0.01
    # Historical AgI base used only for legacy INA/kg ref surface calc
    reference_efficiency: float = 1.0


def relative_ina_score(overall_efficiency: float, reference_efficiency: float = 1.0) -> float:
    """Map overall efficiency to relative score.

    With the empirical peak×a(T) model, overall is already relative to AgI peak
    (AgI peak_strength = 1). reference_efficiency defaults to 1.0 (identity).
    """
    if reference_efficiency <= 0:
        return 0.0
    return max(0.0, overall_efficiency / reference_efficiency)


def ina_per_kg_proxy(
    candidate: Candidate,
    overall_efficiency: float,
    assumptions: ParticleAssumptions | None = None,
    diameter_um: float | None = None,
) -> float | None:
    """Relative ice-active surface × score per kg (assumption-dependent)."""
    assumptions = assumptions or ParticleAssumptions()
    d_um = diameter_um if diameter_um is not None else assumptions.diameter_um
    rho = candidate.density_g_cm3
    if rho is None or rho <= 0:
        return None
    d_m = d_um * 1e-6
    rho_kg_m3 = rho * 1000.0
    ssa_m2_kg = 6.0 / (rho_kg_m3 * d_m)
    activity = ssa_m2_kg * assumptions.active_site_fraction * overall_efficiency
    ref_ssa = 6.0 / (5670.0 * d_m)  # AgI density 5.67 g/cm³
    ref_activity = (
        ref_ssa * assumptions.active_site_fraction * assumptions.reference_efficiency
    )
    if ref_activity <= 0:
        return None
    return activity / ref_activity

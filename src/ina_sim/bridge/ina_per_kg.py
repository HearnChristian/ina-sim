"""Particle/bulk bridge: molecular/heuristic activity → engineering INA/kg proxy.

These are **assumption-dependent** order-of-magnitude helpers for payload
conversations, not lab-calibrated ice-nucleating particle (INP) concentrations.
Always surface assumptions next to the number.
"""

from __future__ import annotations

from dataclasses import dataclass

from ina_sim.models.candidate import Candidate


@dataclass(frozen=True)
class ParticleAssumptions:
    """Default spherical monodisperse particle assumptions."""

    diameter_um: float = 1.0
    active_site_fraction: float = 0.01  # fraction of surface that is ice-active
    # Reference efficiency (AgI-like) used for relative scaling
    reference_efficiency: float = 0.85


def relative_ina_score(overall_efficiency: float, reference_efficiency: float = 0.85) -> float:
    """Score relative to a reference agent efficiency (default ~AgI base)."""
    if reference_efficiency <= 0:
        return 0.0
    return overall_efficiency / reference_efficiency


def ina_per_kg_proxy(
    candidate: Candidate,
    overall_efficiency: float,
    assumptions: ParticleAssumptions | None = None,
) -> float | None:
    """Rough 'effective ice-active surface × efficiency per kg' proxy.

    Returns a unitless relative figure of merit scaled so denser / more
    efficient agents score higher. Not comparable to measured #INP/L without
    calibration.

    formula (conceptual):
        SSA ~ 6 / (rho * d)          # m²/kg for spheres
        activity ~ SSA * f_active * efficiency
        report activity / activity_ref  (relative)
    """
    assumptions = assumptions or ParticleAssumptions()
    rho = candidate.density_g_cm3
    if rho is None or rho <= 0:
        return None
    # diameter m, density kg/m³
    d_m = assumptions.diameter_um * 1e-6
    rho_kg_m3 = rho * 1000.0
    ssa_m2_kg = 6.0 / (rho_kg_m3 * d_m)
    activity = ssa_m2_kg * assumptions.active_site_fraction * overall_efficiency
    # Normalize by a fixed reference (AgI-like at base efficiency, rho=5.67)
    ref_ssa = 6.0 / (5670.0 * d_m)
    ref_activity = (
        ref_ssa * assumptions.active_site_fraction * assumptions.reference_efficiency
    )
    if ref_activity <= 0:
        return None
    return activity / ref_activity

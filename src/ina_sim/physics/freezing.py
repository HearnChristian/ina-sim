"""From parameterizations to things a laboratory actually measures.

An ns(T) value on its own is not an observable. What a droplet-freezing assay
reports is a frozen fraction, a median freezing temperature, or an INP
concentration, and those are what this module computes, so predictions here can
be compared against published measurements rather than admired in isolation.

Two descriptions are implemented, and they are not interchangeable:

singular (Vali, 1971)
    Each particle carries a temperature-ordered set of active sites; freezing
    is time independent. Frozen fraction of droplets each carrying surface
    area A:
        f(T) = 1 - exp(-ns(T) * A)
    inverted by
        ns(T) = -ln(1 - f) / A

stochastic (Murray et al., 2011, Eqs. 16-19)
    Nucleation is a rate process; the survival probability of a droplet with
    particle surface area sigma and volume V over a time step dt is
        f = 1 - exp(-(J_hom * V + J_het * sigma) * dt)
    so the answer depends on cooling rate. Real immersion data sit between the
    two descriptions; the difference between them is a useful honesty check and
    is reported, not hidden.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ina_sim.physics.ns import Estimate, Parameterization, evaluate
from ina_sim.units import CM2_PER_M2, CM3_PER_M3, sphere_surface_area_m2

LN2 = math.log(2.0)

# Numerical guard: exp(-x) underflows to 0 for x > ~745, which is the correct
# limit (everything frozen) but we clamp to keep 1 - exp() exactly 1.0.
_MAX_EXPONENT = 700.0


def frozen_fraction_singular(ns_m2: float, area_m2: float) -> float:
    """Fraction of droplets frozen, singular description. Dimensionless [0, 1]."""
    if ns_m2 < 0 or area_m2 < 0:
        raise ValueError("ns and area must be non-negative")
    x = ns_m2 * area_m2
    if not math.isfinite(x):
        return 1.0
    if x > _MAX_EXPONENT:
        return 1.0
    return 1.0 - math.exp(-x)


def ns_from_frozen_fraction(frozen_fraction: float, area_m2: float) -> float:
    """Vali (1971) singular inversion. Returns ns in m^-2.

    Undefined at f = 0 (no information) and f = 1 (-ln(0) diverges); both raise
    rather than return a misleading number.
    """
    if not 0.0 < frozen_fraction < 1.0:
        raise ValueError(
            "frozen_fraction must be strictly between 0 and 1 to invert; "
            "f=0 carries no information and f=1 diverges"
        )
    if area_m2 <= 0:
        raise ValueError("area_m2 must be positive")
    return -math.log(1.0 - frozen_fraction) / area_m2


def inp_concentration_per_m3(
    ns_m2: float,
    particle_number_per_m3: float,
    particle_diameter_m: float,
) -> float:
    """INP concentration from an aerosol population and an ns value.

    Uses the exact per-particle activation probability
        n_INP = N * (1 - exp(-ns * A_particle))
    rather than the linearised N * ns * A, so the result saturates at N instead
    of exceeding the number of particles present when ns * A is large.
    """
    if particle_number_per_m3 < 0:
        raise ValueError("particle_number_per_m3 must be non-negative")
    area = sphere_surface_area_m2(particle_diameter_m)
    return particle_number_per_m3 * frozen_fraction_singular(ns_m2, area)


def frozen_fraction_stochastic(
    *,
    j_het_cm2_s: float = 0.0,
    particle_area_cm2: float = 0.0,
    j_hom_cm3_s: float = 0.0,
    droplet_volume_cm3: float = 0.0,
    dt_s: float = 1.0,
) -> float:
    """Murray et al. (2011) Eq. (18): freezing over one time step.

    Rate coefficients stay in the CGS units the source quotes them in.
    """
    if dt_s < 0:
        raise ValueError("dt_s must be non-negative")
    rate = j_het_cm2_s * particle_area_cm2 + j_hom_cm3_s * droplet_volume_cm3
    if rate < 0:
        raise ValueError("nucleation rates must be non-negative")
    x = rate * dt_s
    if x > _MAX_EXPONENT:
        return 1.0
    return 1.0 - math.exp(-x)


@dataclass(frozen=True)
class FreezingPoint:
    """Predicted frozen fraction at one temperature, with its uncertainty band."""

    temperature_c: float
    frozen_fraction: float
    frozen_fraction_low: float
    frozen_fraction_high: float
    ns_m2: float | None
    in_range: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "T_c": round(self.temperature_c, 3),
            "frozen_fraction": round(self.frozen_fraction, 5),
            "frozen_fraction_low": round(self.frozen_fraction_low, 5),
            "frozen_fraction_high": round(self.frozen_fraction_high, 5),
            "ns_m2": self.ns_m2,
            "in_range": self.in_range,
        }


def freezing_curve(
    param: Parameterization,
    *,
    droplet_surface_area_m2: float,
    t_start_c: float | None = None,
    t_end_c: float | None = None,
    step_c: float = 0.5,
    allow_extrapolation: bool = False,
) -> list[FreezingPoint]:
    """Predicted droplet-freezing curve over the parameterization's own range.

    Defaults to exactly the temperature interval the source fitted, which is
    the only interval where the curve means anything.
    """
    if param.quantity != "ns":
        raise ValueError(
            f"{param.id} is a rate parameterization; use stochastic_freezing_curve"
        )
    if droplet_surface_area_m2 <= 0:
        raise ValueError("droplet_surface_area_m2 must be positive")
    if step_c <= 0:
        raise ValueError("step_c must be positive")

    lo = param.t_min_c if t_start_c is None else min(t_start_c, t_end_c or t_start_c)
    hi = param.t_max_c if t_end_c is None else max(t_start_c or t_end_c, t_end_c)
    out: list[FreezingPoint] = []
    n_steps = int(round((hi - lo) / step_c))
    for i in range(n_steps + 1):
        temp = hi - i * step_c
        est = evaluate(param, temp, allow_extrapolation=allow_extrapolation)
        if est.value is None:
            out.append(
                FreezingPoint(temp, 0.0, 0.0, 0.0, None, est.in_range)
            )
            continue
        out.append(
            FreezingPoint(
                temperature_c=temp,
                frozen_fraction=frozen_fraction_singular(est.value, droplet_surface_area_m2),
                frozen_fraction_low=frozen_fraction_singular(
                    est.low or 0.0, droplet_surface_area_m2
                ),
                frozen_fraction_high=frozen_fraction_singular(
                    est.high or 0.0, droplet_surface_area_m2
                ),
                ns_m2=est.value,
                in_range=est.in_range,
            )
        )
    return out


def median_freezing_temperature(
    param: Parameterization,
    droplet_surface_area_m2: float,
    *,
    tolerance_c: float = 1e-3,
) -> float | None:
    """Temperature where half the droplets have frozen (T50), or None.

    Solves ns(T) * A = ln 2 by bisection inside the parameterization's range.
    Returns None when the crossing lies outside that range, because the answer
    would be an extrapolation dressed up as a prediction. T50 is directly
    comparable with published median freezing temperatures.
    """
    if param.quantity != "ns":
        raise ValueError(f"{param.id} is a rate parameterization; T50 needs ns")
    if droplet_surface_area_m2 <= 0:
        raise ValueError("droplet_surface_area_m2 must be positive")

    target = LN2 / droplet_surface_area_m2

    warm = evaluate(param, param.t_max_c)
    cold = evaluate(param, param.t_min_c)
    if warm.value is None or cold.value is None:
        return None
    if warm.value >= target:
        return None  # already past half-frozen at the warm end of validity
    if cold.value <= target:
        return None  # never reaches half-frozen inside the valid range

    lo, hi = param.t_min_c, param.t_max_c
    while hi - lo > tolerance_c:
        mid = 0.5 * (lo + hi)
        est = evaluate(param, mid)
        if est.value is None:
            return None
        if est.value >= target:
            lo = mid  # colder side still above target -> move up
        else:
            hi = mid
    return round(0.5 * (lo + hi), 4)


def stochastic_freezing_curve(
    het_param: Parameterization | None,
    *,
    particle_area_m2: float,
    droplet_volume_m3: float,
    cooling_rate_k_per_min: float = 1.0,
    hom_param: Parameterization | None = None,
    t_start_c: float,
    t_end_c: float,
    step_c: float = 0.1,
) -> list[dict[str, Any]]:
    """Cooling-ramp integration of Murray et al. (2011) Eqs. (16)-(22).

    Walks down in temperature steps, converts each step to a dwell time from
    the cooling rate, and accumulates the survival probability. Because it is a
    rate model the result depends on cooling_rate_k_per_min - that dependence is
    the physical content, not a bug.
    """
    if cooling_rate_k_per_min <= 0:
        raise ValueError("cooling_rate_k_per_min must be positive")
    if step_c <= 0:
        raise ValueError("step_c must be positive")
    if particle_area_m2 < 0 or droplet_volume_m3 < 0:
        raise ValueError("area and volume must be non-negative")

    area_cm2 = particle_area_m2 * CM2_PER_M2
    volume_cm3 = droplet_volume_m3 * CM3_PER_M3
    dt_s = (step_c / cooling_rate_k_per_min) * 60.0

    hi, lo = max(t_start_c, t_end_c), min(t_start_c, t_end_c)
    n_steps = int(round((hi - lo) / step_c))
    survival = 1.0
    out: list[dict[str, Any]] = []
    for i in range(n_steps + 1):
        temp = hi - i * step_c
        j_het = 0.0
        het_in_range = False
        if het_param is not None:
            est = evaluate(het_param, temp)
            het_in_range = est.in_range
            j_het = est.value or 0.0
        j_hom = 0.0
        hom_in_range = False
        if hom_param is not None:
            est_h = evaluate(hom_param, temp)
            hom_in_range = est_h.in_range
            j_hom = est_h.value or 0.0
        step_fraction = frozen_fraction_stochastic(
            j_het_cm2_s=j_het,
            particle_area_cm2=area_cm2,
            j_hom_cm3_s=j_hom,
            droplet_volume_cm3=volume_cm3,
            dt_s=dt_s,
        )
        survival *= 1.0 - step_fraction
        out.append(
            {
                "T_c": round(temp, 3),
                "frozen_fraction": round(1.0 - survival, 5),
                "j_het_cm2_s": j_het,
                "j_hom_cm3_s": j_hom,
                "het_in_range": het_in_range,
                "hom_in_range": hom_in_range,
            }
        )
    return out


def compare_descriptions(
    singular: Estimate,
    *,
    droplet_surface_area_m2: float,
    stochastic_curve: list[dict[str, Any]],
) -> dict[str, Any]:
    """Report where the singular and stochastic descriptions disagree.

    Disagreement is expected and informative: singular freezing has no time
    dependence, stochastic freezing does.
    """
    singular_f = (
        None
        if singular.value is None
        else frozen_fraction_singular(singular.value, droplet_surface_area_m2)
    )
    match = next(
        (p for p in stochastic_curve if abs(p["T_c"] - singular.temperature_c) < 1e-6),
        None,
    )
    return {
        "T_c": singular.temperature_c,
        "singular_frozen_fraction": singular_f,
        "stochastic_frozen_fraction": None if match is None else match["frozen_fraction"],
        "note": (
            "singular freezing is time independent; the stochastic value depends "
            "on cooling rate. A gap between them bounds how much of the answer is "
            "model choice rather than measurement."
        ),
    }

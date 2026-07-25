"""Polydisperse aerosol: from a size distribution to an INP concentration.

Everywhere else in this package a particle population is monodisperse spheres,
which is fine for a single-material screen and wrong for atmospheric work. Real
aerosol is a sum of lognormal modes, and it is the *surface area* integral over
those modes that ns(T) multiplies - so the answer moves by orders of magnitude
depending on the distribution, not just its mean size.

A lognormal mode with count median diameter D_g and geometric standard
deviation sigma_g has the Hatch-Choate moments (Seinfeld and Pandis, 2016):

    <D^k> = D_g^k exp(k^2 ln^2(sigma_g) / 2)

so total surface area and volume per unit air volume are

    S_tot = N pi D_g^2 exp(2 ln^2 sigma_g)
    V_tot = N (pi/6) D_g^3 exp(4.5 ln^2 sigma_g)

The INP concentration is **not** ns * S_tot. That linearisation counts multiple
active sites on one particle as multiple INP and can exceed the number of
particles present. The correct quantity integrates the per-particle activation
probability over the distribution:

    n_INP = integral n(D) [1 - exp(-ns pi D^2)] dD

which reduces to ns * S_tot only in the dilute limit ns*A << 1. Both are
reported, along with their ratio, because the gap between them tells you
whether you are in the regime where the usual linear formula is safe.

Truncation matters too: instruments count over a finite size range, and INP
parameterizations built on "particles larger than 0.5 um" are not comparable to
an untruncated integral. `d_min_um` / `d_max_um` make that explicit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ina_sim.physics.ns import Estimate, Parameterization, evaluate
from ina_sim.units import micrometres_to_metres, sphere_surface_area_m2

# Integration half-width in units of ln(sigma_g). +/-5 covers all but ~3e-7 of
# the distribution, well below any uncertainty in ns itself.
_LN_SIGMA_SPAN = 5.0
_DEFAULT_BINS = 240


@dataclass(frozen=True)
class LognormalMode:
    """One lognormal aerosol mode, described the way instruments report it."""

    number_per_cm3: float
    median_diameter_um: float  # count median diameter
    geometric_sd: float  # sigma_g, dimensionless and > 1
    name: str = ""

    def __post_init__(self) -> None:
        if self.number_per_cm3 < 0:
            raise ValueError("number_per_cm3 must be non-negative")
        if self.median_diameter_um <= 0:
            raise ValueError("median_diameter_um must be positive")
        if self.geometric_sd <= 1.0:
            raise ValueError(
                "geometric_sd must exceed 1 (sigma_g = 1 is monodisperse; use "
                "a value just above 1 to approximate it)"
            )

    @property
    def number_per_m3(self) -> float:
        return self.number_per_cm3 * 1e6

    @property
    def median_diameter_m(self) -> float:
        return micrometres_to_metres(self.median_diameter_um)

    def moment(self, k: int) -> float:
        """Hatch-Choate: <D^k> in metres^k."""
        ln_sd = math.log(self.geometric_sd)
        return self.median_diameter_m**k * math.exp(k * k * ln_sd * ln_sd / 2.0)

    @property
    def surface_area_m2_per_m3(self) -> float:
        """Analytic total surface area, untruncated."""
        return self.number_per_m3 * math.pi * self.moment(2)

    @property
    def volume_m3_per_m3(self) -> float:
        return self.number_per_m3 * math.pi * self.moment(3) / 6.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name or None,
            "number_per_cm3": self.number_per_cm3,
            "median_diameter_um": self.median_diameter_um,
            "geometric_sd": self.geometric_sd,
            "surface_area_m2_per_m3": self.surface_area_m2_per_m3,
        }


@dataclass(frozen=True)
class SizeDistribution:
    """A sum of lognormal modes, optionally truncated to an instrument range."""

    modes: tuple[LognormalMode, ...]
    d_min_um: float | None = None
    d_max_um: float | None = None

    def __post_init__(self) -> None:
        if not self.modes:
            raise ValueError("a size distribution needs at least one mode")
        if self.d_min_um is not None and self.d_min_um <= 0:
            raise ValueError("d_min_um must be positive")
        if (
            self.d_min_um is not None
            and self.d_max_um is not None
            and self.d_max_um <= self.d_min_um
        ):
            raise ValueError("d_max_um must exceed d_min_um")

    @property
    def truncated(self) -> bool:
        return self.d_min_um is not None or self.d_max_um is not None

    def bins(self, n_bins: int = _DEFAULT_BINS) -> list[tuple[float, float]]:
        """Discretise into (diameter_m, number_per_m3) pairs.

        Uniform in ln D, midpoint rule, one set of bins per mode. Bins outside
        the truncation limits are dropped rather than clipped, so a truncated
        distribution really does contain fewer particles.
        """
        if n_bins < 2:
            raise ValueError("n_bins must be at least 2")
        out: list[tuple[float, float]] = []
        lo_m = micrometres_to_metres(self.d_min_um) if self.d_min_um else None
        hi_m = micrometres_to_metres(self.d_max_um) if self.d_max_um else None

        for mode in self.modes:
            ln_sd = math.log(mode.geometric_sd)
            ln_median = math.log(mode.median_diameter_m)
            ln_lo = ln_median - _LN_SIGMA_SPAN * ln_sd
            ln_hi = ln_median + _LN_SIGMA_SPAN * ln_sd
            step = (ln_hi - ln_lo) / n_bins
            norm = mode.number_per_m3 / (math.sqrt(2.0 * math.pi) * ln_sd)
            for i in range(n_bins):
                ln_d = ln_lo + (i + 0.5) * step
                diameter = math.exp(ln_d)
                if lo_m is not None and diameter < lo_m:
                    continue
                if hi_m is not None and diameter > hi_m:
                    continue
                delta = (ln_d - ln_median) / ln_sd
                number = norm * math.exp(-0.5 * delta * delta) * step
                out.append((diameter, number))
        out.sort(key=lambda pair: pair[0])
        return out

    def total_number_per_m3(self, n_bins: int = _DEFAULT_BINS) -> float:
        if not self.truncated:
            return sum(m.number_per_m3 for m in self.modes)
        return sum(n for _, n in self.bins(n_bins))

    def surface_area_m2_per_m3(self, n_bins: int = _DEFAULT_BINS) -> float:
        """Total aerosol surface area per cubic metre of air."""
        if not self.truncated:
            return sum(m.surface_area_m2_per_m3 for m in self.modes)
        return sum(
            n * sphere_surface_area_m2(d) for d, n in self.bins(n_bins)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "modes": [m.as_dict() for m in self.modes],
            "d_min_um": self.d_min_um,
            "d_max_um": self.d_max_um,
            "truncated": self.truncated,
            "total_number_per_cm3": self.total_number_per_m3() / 1e6,
            "surface_area_m2_per_m3": self.surface_area_m2_per_m3(),
        }


@dataclass(frozen=True)
class InpConcentration:
    """INP concentration from one ns value and one size distribution."""

    temperature_c: float
    ns_m2: float
    n_inp_per_litre: float
    n_inp_linear_per_litre: float
    n_inp_low_per_litre: float | None
    n_inp_high_per_litre: float | None
    surface_area_m2_per_m3: float
    total_number_per_cm3: float
    activated_fraction: float
    linear_ratio: float
    d50_contribution_um: float | None
    fraction_from_coarse: float
    coarse_threshold_um: float
    parameterization_id: str
    citation: str
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "T_c": round(self.temperature_c, 4),
            "ns_m2": self.ns_m2,
            "n_inp_per_litre": self.n_inp_per_litre,
            "n_inp_low_per_litre": self.n_inp_low_per_litre,
            "n_inp_high_per_litre": self.n_inp_high_per_litre,
            "n_inp_linear_per_litre": self.n_inp_linear_per_litre,
            "linear_ratio": round(self.linear_ratio, 4),
            "surface_area_m2_per_m3": self.surface_area_m2_per_m3,
            "total_number_per_cm3": self.total_number_per_cm3,
            "activated_fraction": self.activated_fraction,
            "d50_contribution_um": self.d50_contribution_um,
            "fraction_from_coarse": round(self.fraction_from_coarse, 4),
            "coarse_threshold_um": self.coarse_threshold_um,
            "parameterization": self.parameterization_id,
            "citation": self.citation,
            "notes": list(self.notes),
        }


def _inp_per_m3(
    bins: list[tuple[float, float]], ns_m2: float
) -> tuple[float, list[tuple[float, float]]]:
    """Exact integral of the per-particle activation probability."""
    total = 0.0
    per_bin: list[tuple[float, float]] = []
    for diameter, number in bins:
        area = sphere_surface_area_m2(diameter)
        exponent = ns_m2 * area
        activated = 1.0 if exponent > 700.0 else 1.0 - math.exp(-exponent)
        contribution = number * activated
        total += contribution
        per_bin.append((diameter, contribution))
    return total, per_bin


def inp_concentration(
    distribution: SizeDistribution,
    estimate: Estimate,
    *,
    n_bins: int = _DEFAULT_BINS,
    coarse_threshold_um: float = 1.0,
) -> InpConcentration | None:
    """INP concentration for an aerosol population, or None if ns is unavailable.

    Returns None when the parameterization declines to give a value at this
    temperature - an aerosol population cannot rescue an out-of-range fit.
    """
    if estimate.quantity != "ns":
        raise ValueError(
            f"{estimate.parameterization_id} is a rate coefficient; an INP "
            "concentration needs a site density"
        )
    if estimate.value is None:
        return None

    bins = distribution.bins(n_bins)
    if not bins:
        raise ValueError(
            "the truncation limits exclude the entire size distribution"
        )
    total_number = sum(n for _, n in bins)
    surface = sum(n * sphere_surface_area_m2(d) for d, n in bins)

    n_inp, per_bin = _inp_per_m3(bins, estimate.value)
    low = _inp_per_m3(bins, estimate.low)[0] if estimate.low else None
    high = _inp_per_m3(bins, estimate.high)[0] if estimate.high else None
    linear = estimate.value * surface

    # Which sizes actually carry the ice nucleation?
    cumulative = 0.0
    d50: float | None = None
    coarse = 0.0
    threshold_m = micrometres_to_metres(coarse_threshold_um)
    for diameter, contribution in per_bin:
        cumulative += contribution
        if d50 is None and n_inp > 0 and cumulative >= 0.5 * n_inp:
            d50 = diameter * 1e6
        if diameter >= threshold_m:
            coarse += contribution

    notes: list[str] = list(estimate.notes)
    ratio = linear / n_inp if n_inp > 0 else float("nan")
    if math.isfinite(ratio) and ratio > 1.1:
        notes.append(
            f"the usual linear formula ns x S_tot overstates this by "
            f"{ratio:.2g}x: particles here carry many active sites each, so "
            "the linearisation double counts"
        )
    if distribution.truncated:
        notes.append(
            "size range truncated; compare only with measurements over the "
            "same range"
        )

    return InpConcentration(
        temperature_c=estimate.temperature_c,
        ns_m2=estimate.value,
        n_inp_per_litre=n_inp * 1e-3,
        n_inp_linear_per_litre=linear * 1e-3,
        n_inp_low_per_litre=None if low is None else low * 1e-3,
        n_inp_high_per_litre=None if high is None else high * 1e-3,
        surface_area_m2_per_m3=surface,
        total_number_per_cm3=total_number / 1e6,
        activated_fraction=n_inp / total_number if total_number > 0 else 0.0,
        linear_ratio=ratio,
        d50_contribution_um=d50,
        fraction_from_coarse=coarse / n_inp if n_inp > 0 else 0.0,
        coarse_threshold_um=coarse_threshold_um,
        parameterization_id=estimate.parameterization_id,
        citation=estimate.citation,
        notes=tuple(notes),
    )


def inp_spectrum(
    distribution: SizeDistribution,
    param: Parameterization,
    *,
    t_min_c: float | None = None,
    t_max_c: float | None = None,
    step_c: float = 1.0,
    n_bins: int = _DEFAULT_BINS,
) -> list[InpConcentration]:
    """INP concentration across a temperature range, inside the fitted range."""
    if step_c <= 0:
        raise ValueError("step_c must be positive")
    lo = param.t_min_c if t_min_c is None else max(t_min_c, param.t_min_c)
    hi = param.t_max_c if t_max_c is None else min(t_max_c, param.t_max_c)
    if hi < lo:
        return []
    out: list[InpConcentration] = []
    n_steps = int(round((hi - lo) / step_c))
    for i in range(n_steps + 1):
        temp = hi - i * step_c
        result = inp_concentration(
            distribution, evaluate(param, temp), n_bins=n_bins
        )
        if result is not None:
            out.append(result)
    return out


def parse_mode(spec: str) -> LognormalMode:
    """Parse `N:Dg:sigma[:name]` with N in cm^-3 and Dg in micrometres."""
    parts = [p.strip() for p in spec.split(":")]
    if len(parts) < 3:
        raise ValueError(
            f"mode {spec!r} must be number_per_cm3:median_diameter_um:sigma_g "
            "(optionally :name), e.g. 1.0:0.8:1.9:accumulation"
        )
    try:
        number, diameter, sigma = (float(parts[0]), float(parts[1]), float(parts[2]))
    except ValueError as exc:
        raise ValueError(f"mode {spec!r}: all three values must be numbers") from exc
    return LognormalMode(
        number_per_cm3=number,
        median_diameter_um=diameter,
        geometric_sd=sigma,
        name=parts[3] if len(parts) > 3 else "",
    )

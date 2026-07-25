"""Particle size and dose: making the inputs that should matter, matter.

Before this module the screening score ignored particle diameter entirely and
saturated in seeding density at an arbitrary 50 particles per litre, so four of
the six sliders in the GUI changed nothing. Two of those were honest (pressure
and, in immersion mode, relative humidity really do not decide whether a droplet
freezes) and two were not.

**Size.** The probability that one particle of diameter d nucleates ice is

    P_act = 1 - exp(-ns(T) * pi * d^2)

so it scales with surface area, as d^2. Marcolli et al. (2016) measured a ~28 K
swing in freezing temperature between 20 nm and 40 nm AgI particles; a model
where diameter does nothing cannot represent that.

For materials with a published parameterization, ns(T) is the measured value -
and **only** where that parameterization is valid. A measured material outside
its fitted temperature range gets no activation at all, exactly as it gets no
ns: falling back to the heuristic there produced a seven-order-of-magnitude jump
at the edge of the fit, which is worse than no answer.

For materials that were never measured there is no ns, so the heuristic score is
**reinterpreted** as the per-particle activation probability at a 1 um reference
diameter:

    ns_eff(T) = -ln(1 - eta(T)) / (pi * d_ref^2)

This is a convention, not a measurement, and it is labelled as one everywhere it
appears. Its one virtue is exactness at the reference: at d = 1 um the activation
probability equals the score the tool has always reported, so nothing that
already worked changes, while away from 1 um the size dependence is the physical
d^2 rather than nothing at all.

**Dose.** Ice nucleating particle concentration is linear in the number of
particles supplied:

    n_INP = N * P_act

with no saturation, and that is what this module reports. The relative score
keeps its legacy loading factor min(1, N/50), which saturates at 50 per litre
for no physical reason; it is retained because "zero dose gives zero score" is
an intended and tested property of that score, and because it multiplies every
candidate equally and so cannot change a ranking. Read n_INP, not the score,
for anything dose related.

Real seeding does saturate - overseeding, where too many ice crystals compete
for the same vapour and none grows to precipitation size - but that is a vapour
budget and growth problem, not a nucleation one, and it is NOT modelled here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ina_sim.physics.freezing import frozen_fraction_singular
from ina_sim.units import micrometres_to_metres, sphere_surface_area_m2

REFERENCE_DIAMETER_UM = 1.0
"""Diameter at which the heuristic score is defined to be the activation
probability. Chosen because it is the library's own default particle size, so
existing results are preserved exactly."""

# eta arbitrarily close to 1 would give an infinite effective ns.
_MAX_SCORE = 1.0 - 1e-9


@dataclass(frozen=True)
class Activation:
    """Per-particle activation and the dose that follows from it."""

    temperature_c: float
    particle_diameter_um: float
    particle_area_m2: float
    ns_m2: float | None
    ns_source: str  # measured | heuristic_reference | out_of_fitted_range
    activation_probability: float | None
    seeding_density_per_l: float
    n_inp_per_litre: float | None
    reference_diameter_um: float
    citation: str | None = None
    note: str | None = None

    @property
    def available(self) -> bool:
        return self.activation_probability is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "T_c": round(self.temperature_c, 4),
            "particle_diameter_um": self.particle_diameter_um,
            "particle_area_m2": self.particle_area_m2,
            "ns_m2": self.ns_m2,
            "ns_source": self.ns_source,
            "available": self.available,
            # Not rounded: activation probabilities run down to 1e-12 and
            # rounding produced a displayed zero next to a non-zero n_INP.
            "activation_probability": self.activation_probability,
            "seeding_density_per_l": self.seeding_density_per_l,
            "n_inp_per_litre": self.n_inp_per_litre,
            "reference_diameter_um": self.reference_diameter_um,
            "citation": self.citation,
            "note": self.note,
        }


def effective_ns_from_score(
    score: float, *, reference_diameter_um: float = REFERENCE_DIAMETER_UM
) -> float:
    """Invert the heuristic score into an ns that reproduces it at d_ref.

    A convention for materials with no measured ns, not a measurement.
    """
    if not 0.0 <= score <= 1.0:
        raise ValueError("score must be in [0, 1]")
    if reference_diameter_um <= 0:
        raise ValueError("reference diameter must be positive")
    area = sphere_surface_area_m2(micrometres_to_metres(reference_diameter_um))
    clipped = min(score, _MAX_SCORE)
    if clipped <= 0.0:
        return 0.0
    return -math.log(1.0 - clipped) / area


def activation(
    *,
    temperature_c: float,
    score: float,
    particle_diameter_um: float,
    seeding_density_per_l: float,
    measured_ns_m2: float | None = None,
    is_measured_material: bool = False,
    measured_quantity: str = "ns",
    citation: str | None = None,
    reference_diameter_um: float = REFERENCE_DIAMETER_UM,
) -> Activation:
    """Activation probability and INP concentration for one candidate.

    Four outcomes, and which one happened is always recorded in `ns_source`:

        measured             an ns parameterization covers this material here
        out_of_fitted_range  it is measured, but not at this temperature, so no
                             value is returned - the heuristic is NOT substituted
        rate_not_density     it is measured as a nucleation rate coefficient,
                             which is not a site density and cannot be turned
                             into one without a dwell time
        heuristic_reference  nobody measured this material, so the score is read
                             as an activation probability at the reference size
    """
    if particle_diameter_um <= 0:
        raise ValueError("particle_diameter_um must be positive")
    if seeding_density_per_l < 0:
        raise ValueError("seeding_density_per_l must be non-negative")

    area = sphere_surface_area_m2(micrometres_to_metres(particle_diameter_um))

    def _unavailable(source: str, note: str) -> Activation:
        return Activation(
            temperature_c=temperature_c,
            particle_diameter_um=particle_diameter_um,
            particle_area_m2=area,
            ns_m2=None,
            ns_source=source,
            activation_probability=None,
            seeding_density_per_l=seeding_density_per_l,
            n_inp_per_litre=None,
            reference_diameter_um=reference_diameter_um,
            citation=citation,
            note=note,
        )

    if is_measured_material and measured_quantity != "ns":
        # J [cm^-2 s^-1] is not n_s [m^-2]. Feeding one to the other is exactly
        # the unit confusion this package exists to prevent.
        return _unavailable(
            "rate_not_density",
            "this material is measured as a nucleation rate coefficient, not a "
            "site density; an activation probability from a rate needs a dwell "
            "time, which a steady-state screen does not have",
        )

    if is_measured_material and not (measured_ns_m2 and measured_ns_m2 > 0):
        return _unavailable(
            "out_of_fitted_range",
            "this material is measured, but not at this temperature; the "
            "heuristic score is deliberately NOT substituted, because doing so "
            "jumps by orders of magnitude at the edge of the fitted range",
        )

    if measured_ns_m2 is not None and measured_ns_m2 > 0:
        ns = measured_ns_m2
        source = "measured"
        note = None
    else:
        ns = effective_ns_from_score(score, reference_diameter_um=reference_diameter_um)
        source = "heuristic_reference"
        note = (
            "no measured ns for this material: the relative score is being read "
            f"as the activation probability of a {reference_diameter_um:g} µm "
            "particle, which fixes the size scaling but is a convention, not a "
            "measurement"
        )

    probability = frozen_fraction_singular(ns, area)
    return Activation(
        temperature_c=temperature_c,
        particle_diameter_um=particle_diameter_um,
        particle_area_m2=area,
        ns_m2=ns,
        ns_source=source,
        activation_probability=probability,
        seeding_density_per_l=seeding_density_per_l,
        n_inp_per_litre=seeding_density_per_l * probability,
        reference_diameter_um=reference_diameter_um,
        citation=citation,
        note=note,
    )


def slider_sensitivity() -> dict[str, dict[str, str]]:
    """What each screening input does, and why - stated rather than implied.

    A slider that changes nothing is not automatically a bug: pressure really
    does not decide whether a droplet freezes. This table is exported in the
    payload so the distinction between 'inert because the physics says so' and
    'inert because the model is thin' is visible in the product.
    """
    return {
        "temperature_c": {
            "effect": "strong",
            "why": "ns(T) rises by roughly 0.2-0.4 decades per kelvin of cooling",
        },
        "particle_diameter_um": {
            "effect": "strong",
            "why": (
                "activation probability is 1 - exp(-ns * pi d^2), so surface "
                "area and therefore effect scale as d^2"
            ),
        },
        "seeding_density_per_l": {
            "effect": "linear on INP concentration; on the score, linear below 50/L then flat",
            "why": (
                "n_INP = N * P_act is linear in dose with no cap, and that is "
                "the physical quantity. The relative score additionally carries "
                "a legacy loading factor min(1, N/50) that saturates at 50 per "
                "litre; the threshold has no physical basis and it multiplies "
                "every candidate equally, so it scales the scores without "
                "changing their order. Overseeding, where excess crystals "
                "compete for the same vapour, is real and is NOT modelled"
            ),
        },
        "relative_humidity_pct": {
            "effect": "none in immersion, strong in deposition",
            "why": (
                "an immersed particle is already in liquid water, so added "
                "humidity changes nothing about freezing. Deposition nucleation "
                "is controlled by ice supersaturation - properly it needs "
                "ns(T, S_ice), which this build does not have"
            ),
        },
        "pressure_hpa": {
            "effect": "none on nucleation, sets the parcel water inventory",
            "why": (
                "immersion freezing has no meaningful direct pressure "
                "dependence across the troposphere; pressure enters the "
                "condensable water calculation instead"
            ),
        },
        "cloud_volume_m3": {
            "effect": "scales totals, not rates or ranking",
            "why": "a larger parcel holds proportionally more water and more particles",
        },
    }

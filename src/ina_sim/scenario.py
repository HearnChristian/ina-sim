"""Payload in, decision out.

Everything else in this package answers a physics question. This answers the
operational one: *given this much material, dispersed at this size into this
much cloud at this temperature, what do I deliver, how sure am I, and what am I
allowed to say about it?*

The chain is short and every link is already tested elsewhere:

    payload mass ─(agent density, particle size distribution)→ particle count
    particle count ─(cloud volume)→ number concentration
    number concentration ─(ns(T), activation integral)→ n_INP per litre
    n_INP ─(Monte Carlo)→ distribution, and P(above threshold)

It can also be run backwards: given a target confidence of clearing a
threshold, solve for the payload mass that achieves it. That is the question an
operator actually has, and bisection on the forward model answers it.

**The assumption that dominates everything.** The material is taken to mix
uniformly through the stated cloud volume. Real plumes do not: they are narrow,
they are sheared, and the fraction of a cloud that ever sees seeding material is
usually small and hard to know. This makes every number here an **upper bound on
delivery**. INA-sim has no plume or transport model and will not pretend
otherwise - the effective volume is yours to choose, and choosing the whole
cloud is optimistic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from ina_sim.physics.aerosol import LognormalMode
from ina_sim.physics.ns import Parameterization
from ina_sim.physics.uncertainty import MonteCarloResult, propagate_inp
from ina_sim.units import micrometres_to_metres

# Bisection bounds for the inverse solve, in kilograms.
MIN_PAYLOAD_KG = 1e-6
MAX_PAYLOAD_KG = 1e6
INVERSE_TOLERANCE = 0.01


@dataclass(frozen=True)
class Payload:
    """A mass of agent, dispersed at a stated size distribution."""

    mass_kg: float
    density_g_cm3: float
    mode: LognormalMode

    def __post_init__(self) -> None:
        if self.mass_kg <= 0:
            raise ValueError("payload mass must be positive")
        if self.density_g_cm3 <= 0:
            raise ValueError("agent density must be positive")

    @property
    def mean_particle_volume_m3(self) -> float:
        """Hatch-Choate third moment: <V> = (pi/6) D_g^3 exp(4.5 ln^2 sigma_g)."""
        ln_sd = math.log(self.mode.geometric_sd)
        d = micrometres_to_metres(self.mode.median_diameter_um)
        return (math.pi / 6.0) * d**3 * math.exp(4.5 * ln_sd * ln_sd)

    @property
    def mean_particle_mass_kg(self) -> float:
        # g/cm^3 -> kg/m^3 is a factor of 1000.
        return self.mean_particle_volume_m3 * self.density_g_cm3 * 1000.0

    @property
    def particle_count(self) -> float:
        return self.mass_kg / self.mean_particle_mass_kg


@dataclass
class ScenarioResult:
    parameterization_id: str
    material: str
    citation: str
    temperature_c: float
    payload_kg: float
    density_g_cm3: float
    median_diameter_um: float
    geometric_sd: float
    cloud_volume_m3: float
    particle_count: float
    number_per_cm3: float
    threshold_per_litre: float
    monte_carlo: MonteCarloResult
    cost_per_kg: float | None = None
    solved_for_payload: bool = False
    target_probability: float | None = None
    claims: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def probability_above_threshold(self) -> float:
        return self.monte_carlo.exceedance(self.threshold_per_litre)

    @property
    def total_cost(self) -> float | None:
        if self.cost_per_kg is None:
            return None
        return self.cost_per_kg * self.payload_kg

    def as_dict(self) -> dict[str, Any]:
        mc = self.monte_carlo.as_dict()
        return {
            "parameterization": self.parameterization_id,
            "material": self.material,
            "citation": self.citation,
            "conditions": {
                "T_c": self.temperature_c,
                "cloud_volume_m3": self.cloud_volume_m3,
            },
            "payload": {
                "mass_kg": self.payload_kg,
                "density_g_cm3": self.density_g_cm3,
                "median_diameter_um": self.median_diameter_um,
                "geometric_sd": self.geometric_sd,
                "particle_count": self.particle_count,
                "number_per_cm3": self.number_per_cm3,
                "solved_for_payload": self.solved_for_payload,
                "target_probability": self.target_probability,
                "cost_per_kg": self.cost_per_kg,
                "total_cost": self.total_cost,
            },
            "delivered": mc["n_inp_per_litre"],
            "threshold_per_litre": self.threshold_per_litre,
            "probability_above_threshold": round(self.probability_above_threshold, 4),
            "variance_share": mc["variance_share"],
            "sampling": {
                "samples_usable": mc["samples_usable"],
                "seed": mc["seed"],
                "out_of_range_fraction": mc["out_of_range_fraction"],
            },
            "claims": self.claims,
            "warnings": self.warnings,
        }


def _number_per_cm3(payload: Payload, cloud_volume_m3: float) -> float:
    if cloud_volume_m3 <= 0:
        raise ValueError("cloud_volume_m3 must be positive")
    return payload.particle_count / cloud_volume_m3 / 1e6


def _claims(param: Parameterization, result: MonteCarloResult) -> dict[str, list[str]]:
    """What this run does and does not support saying out loud."""
    supported = [
        "an expected ice nucleating particle concentration, with an explicit "
        "uncertainty band, under the stated assumptions",
        "the probability of exceeding a stated INP concentration, conditional on "
        "those assumptions holding",
        "a comparison between agents evaluated on the same surface-area basis",
        f"traceability of every number to {result.citation}",
    ]
    refused = [
        "any statement about precipitation, rainfall enhancement or snowpack: "
        "this tool contains no cloud, growth or transport model",
        "operational efficacy, dosage guidance or a recommendation to fly",
        "a claim that seeding caused an observed outcome",
        "a comparison against an agent whose ns was measured on a different "
        "surface-area basis",
    ]
    conditional = [
        "delivery figures assume uniform mixing into the whole stated cloud "
        "volume, so they are an upper bound; a real plume reaches a fraction of it"
    ]
    if param.status == "derived":
        conditional.append(
            f"the {param.material_key} parameterization is derived in this "
            "repository, not published, and carries the scatter of its source data"
        )
    if result.sigma_assumed:
        conditional.append(
            "the ns uncertainty is a documented substitute, not a value the "
            "source states"
        )
    if result.out_of_range_fraction > 0.05:
        conditional.append(
            f"{result.out_of_range_fraction:.0%} of temperature draws fell outside "
            "the fitted range and were discarded"
        )
    return {"supported": supported, "conditional": conditional, "refused": refused}


def run_scenario(
    param: Parameterization,
    *,
    payload_kg: float,
    density_g_cm3: float,
    median_diameter_um: float,
    geometric_sd: float = 1.8,
    cloud_volume_m3: float = 1e9,
    temperature_c: float = -12.0,
    threshold_per_litre: float = 1.0,
    cost_per_kg: float | None = None,
    samples: int = 4000,
    seed: int = 20260725,
    temperature_sigma_k: float = 0.5,
    payload_relative_sigma: float = 0.15,
    diameter_relative_sigma: float = 0.20,
) -> ScenarioResult:
    """Forward scenario: this much payload delivers this, with this confidence.

    Uncertainty on the payload is carried as uncertainty on the resulting number
    concentration, which is where it acts.
    """
    payload = Payload(
        mass_kg=payload_kg,
        density_g_cm3=density_g_cm3,
        mode=LognormalMode(1.0, median_diameter_um, geometric_sd),
    )
    number_per_cm3 = _number_per_cm3(payload, cloud_volume_m3)

    monte_carlo = propagate_inp(
        param,
        temperature_c=temperature_c,
        number_per_cm3=number_per_cm3,
        median_diameter_um=median_diameter_um,
        geometric_sd=geometric_sd,
        temperature_sigma_k=temperature_sigma_k,
        number_relative_sigma=payload_relative_sigma,
        diameter_relative_sigma=diameter_relative_sigma,
        threshold_per_litre=threshold_per_litre,
        samples=samples,
        seed=seed,
    )

    warnings = list(monte_carlo.notes)
    warnings.insert(
        0,
        "delivery assumes the payload mixes uniformly through the whole "
        f"{cloud_volume_m3:.3g} m³ cloud volume; a real plume reaches a fraction "
        "of that, so treat this as an upper bound",
    )
    if number_per_cm3 > 100.0:
        warnings.append(
            f"{number_per_cm3:.3g} particles per cm³ is a very high loading — "
            "check the payload, particle size and cloud volume"
        )

    return ScenarioResult(
        parameterization_id=param.id,
        material=param.material,
        citation=param.as_dict()["citation"],
        temperature_c=temperature_c,
        payload_kg=payload_kg,
        density_g_cm3=density_g_cm3,
        median_diameter_um=median_diameter_um,
        geometric_sd=geometric_sd,
        cloud_volume_m3=cloud_volume_m3,
        particle_count=payload.particle_count,
        number_per_cm3=number_per_cm3,
        threshold_per_litre=threshold_per_litre,
        monte_carlo=monte_carlo,
        cost_per_kg=cost_per_kg,
        claims=_claims(param, monte_carlo),
        warnings=warnings,
    )


def solve_payload(
    param: Parameterization,
    *,
    target_probability: float,
    density_g_cm3: float,
    median_diameter_um: float,
    geometric_sd: float = 1.8,
    cloud_volume_m3: float = 1e9,
    temperature_c: float = -12.0,
    threshold_per_litre: float = 1.0,
    cost_per_kg: float | None = None,
    samples: int = 1500,
    seed: int = 20260725,
    **kwargs: Any,
) -> ScenarioResult | None:
    """Inverse scenario: how much payload buys this much confidence?

    Bisects on mass. Returns None when even an absurd payload cannot reach the
    target, which happens when the temperature is simply too warm for the agent -
    a real answer, and a more useful one than a very large number.
    """
    if not 0.0 < target_probability < 1.0:
        raise ValueError("target_probability must be between 0 and 1")

    def probability(mass: float) -> float:
        return run_scenario(
            param,
            payload_kg=mass,
            density_g_cm3=density_g_cm3,
            median_diameter_um=median_diameter_um,
            geometric_sd=geometric_sd,
            cloud_volume_m3=cloud_volume_m3,
            temperature_c=temperature_c,
            threshold_per_litre=threshold_per_litre,
            samples=samples,
            seed=seed,
            **kwargs,
        ).probability_above_threshold

    if probability(MAX_PAYLOAD_KG) < target_probability:
        return None

    lo, hi = MIN_PAYLOAD_KG, MAX_PAYLOAD_KG
    # Bisect in log space: payload spans many orders of magnitude.
    for _ in range(60):
        if math.log10(hi / lo) < INVERSE_TOLERANCE:
            break
        mid = 10 ** (0.5 * (math.log10(lo) + math.log10(hi)))
        if probability(mid) >= target_probability:
            hi = mid
        else:
            lo = mid

    result = run_scenario(
        param,
        payload_kg=hi,
        density_g_cm3=density_g_cm3,
        median_diameter_um=median_diameter_um,
        geometric_sd=geometric_sd,
        cloud_volume_m3=cloud_volume_m3,
        temperature_c=temperature_c,
        threshold_per_litre=threshold_per_litre,
        cost_per_kg=cost_per_kg,
        samples=samples * 2,
        seed=seed,
        **kwargs,
    )
    result.solved_for_payload = True
    result.target_probability = target_probability
    return result

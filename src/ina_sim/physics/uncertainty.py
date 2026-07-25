"""Monte Carlo uncertainty for INP concentration.

A point estimate of an INP concentration is close to useless for a decision. The
inputs are uncertain by wildly different amounts - the AgI parameterization
carries 1.8 decades of scatter while an optical counter knows its number
concentration to maybe 30% - and the output spans orders of magnitude, so the
question worth answering is not "what is n_INP" but "what is the chance n_INP
clears the threshold I care about".

This module answers that by sampling. Three things vary:

    ns(T)        log-normal, because the literature states its uncertainty in
                 decades of log10(ns). A sigma of 0.8 means a factor of ~6 each
                 way at one sigma.
    temperature  normal, and it matters more than people expect: ns changes by
                 0.2-0.4 decades per kelvin, so a +/-0.5 K measurement error is
                 already a factor of ~1.5 in the answer.
    size         log-normal on number concentration and on median diameter,
                 because both are positive quantities with multiplicative
                 instrument error.

It also reports a **variance decomposition**: how much of the spread each input
is responsible for, computed by re-running with that input frozen at its central
value under common random numbers. That is the output that changes behaviour -
it says which measurement to improve to make the answer sharper, and usually the
answer is not the one people expect.

What this does NOT capture, and cannot:

  * structural error - a wrong parameterization, the wrong nucleation mode, or a
    material nobody has measured. Sampling a fit's stated uncertainty says
    nothing about whether the fit is right.
  * correlations between inputs. Every input is drawn independently, which is a
    documented assumption, not a finding.
  * an assumed sigma. Where a source states no uncertainty the substitute is
    used and the result is flagged, so the band is only as honest as its input.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from ina_sim.physics.ns import Parameterization, evaluate
from ina_sim.units import sphere_surface_area_m2

DEFAULT_SAMPLES = 4000
DEFAULT_SEED = 20260725
DEFAULT_BINS = 96
"""Fewer bins than a single deterministic evaluation: the discretisation error
(<0.5%) is negligible beside the uncertainties being sampled, and it keeps a
four-thousand-sample run interactive."""

# Below this fraction of usable samples the result is not trustworthy.
MIN_USABLE_FRACTION = 0.5


@dataclass(frozen=True)
class Uncertain:
    """A central value with a multiplicative or additive 1-sigma spread."""

    central: float
    sigma: float = 0.0
    kind: str = "lognormal_relative"  # lognormal_relative | normal | log10

    @property
    def varies(self) -> bool:
        return self.sigma > 0.0

    def draw(self, rng: random.Random) -> float:
        if not self.varies:
            return self.central
        if self.kind == "normal":
            return rng.gauss(self.central, self.sigma)
        if self.kind == "log10":
            # sigma is in decades: the convention the ns literature uses.
            return self.central * 10.0 ** rng.gauss(0.0, self.sigma)
        # Relative (coefficient of variation) error on a positive quantity.
        cv = self.sigma
        sigma_ln = math.sqrt(math.log1p(cv * cv))
        mu_ln = math.log(self.central) - 0.5 * sigma_ln * sigma_ln
        return math.exp(rng.gauss(mu_ln, sigma_ln))

    def as_dict(self) -> dict[str, Any]:
        return {"central": self.central, "sigma": self.sigma, "kind": self.kind}


@dataclass
class MonteCarloResult:
    parameterization_id: str
    citation: str
    temperature_c: float
    threshold_per_litre: float | None
    samples_requested: int
    samples_usable: int
    seed: int
    values: list[float] = field(default_factory=list)  # n_INP per litre
    out_of_range_fraction: float = 0.0
    sigma_assumed: bool = False
    ns_sigma_used: float = 0.0
    variance_share: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def percentile(self, q: float) -> float:
        """Linear-interpolated percentile, q in [0, 1]."""
        if not self.values:
            return float("nan")
        ordered = sorted(self.values)
        if q <= 0:
            return ordered[0]
        if q >= 1:
            return ordered[-1]
        pos = q * (len(ordered) - 1)
        lo = int(math.floor(pos))
        hi = min(lo + 1, len(ordered) - 1)
        return ordered[lo] + (pos - lo) * (ordered[hi] - ordered[lo])

    @property
    def median(self) -> float:
        return self.percentile(0.5)

    @property
    def geometric_mean(self) -> float:
        positive = [v for v in self.values if v > 0]
        if not positive:
            return 0.0
        return math.exp(sum(math.log(v) for v in positive) / len(positive))

    @property
    def spread_decades(self) -> float:
        """Width of the central 90% interval, in orders of magnitude."""
        lo, hi = self.percentile(0.05), self.percentile(0.95)
        if lo <= 0 or hi <= 0:
            return float("nan")
        return math.log10(hi / lo)

    def exceedance(self, threshold: float) -> float:
        if not self.values:
            return float("nan")
        return sum(1 for v in self.values if v > threshold) / len(self.values)

    def as_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "parameterization": self.parameterization_id,
            "citation": self.citation,
            "T_c": self.temperature_c,
            "seed": self.seed,
            "samples_requested": self.samples_requested,
            "samples_usable": self.samples_usable,
            "out_of_range_fraction": round(self.out_of_range_fraction, 4),
            "sigma_assumed": self.sigma_assumed,
            "ns_sigma_log10_used": self.ns_sigma_used,
            "n_inp_per_litre": {
                "p05": self.percentile(0.05),
                "p16": self.percentile(0.16),
                "p50": self.median,
                "p84": self.percentile(0.84),
                "p95": self.percentile(0.95),
                "geometric_mean": self.geometric_mean,
                "spread_decades_90pct": self.spread_decades,
            },
            "variance_share": {
                k: round(v, 4) for k, v in sorted(
                    self.variance_share.items(), key=lambda kv: -kv[1]
                )
            },
            "notes": list(self.notes),
        }
        if self.threshold_per_litre is not None:
            body["threshold_per_litre"] = self.threshold_per_litre
            body["probability_above_threshold"] = round(
                self.exceedance(self.threshold_per_litre), 4
            )
        return body


def _inp_per_litre(
    ns_m2: float,
    number_per_m3: float,
    median_diameter_m: float,
    geometric_sd: float,
    n_bins: int,
) -> float:
    """One realisation of the activation integral over a single mode."""
    ln_sd = math.log(geometric_sd)
    ln_median = math.log(median_diameter_m)
    ln_lo, ln_hi = ln_median - 5.0 * ln_sd, ln_median + 5.0 * ln_sd
    step = (ln_hi - ln_lo) / n_bins
    norm = number_per_m3 / (math.sqrt(2.0 * math.pi) * ln_sd)
    total = 0.0
    for i in range(n_bins):
        ln_d = ln_lo + (i + 0.5) * step
        diameter = math.exp(ln_d)
        delta = (ln_d - ln_median) / ln_sd
        number = norm * math.exp(-0.5 * delta * delta) * step
        exponent = ns_m2 * sphere_surface_area_m2(diameter)
        activated = 1.0 if exponent > 700.0 else 1.0 - math.exp(-exponent)
        total += number * activated
    return total * 1e-3  # per m^3 -> per litre


def _run_samples(
    param: Parameterization,
    *,
    temperature: Uncertain,
    number_per_cm3: Uncertain,
    median_diameter_um: Uncertain,
    geometric_sd: float,
    samples: int,
    seed: int,
    n_bins: int,
    freeze: str | None = None,
) -> tuple[list[float], int]:
    """Draw samples, optionally freezing one input at its central value.

    Freezing uses the same seed, so the frozen and full runs share random
    numbers and their variances are directly comparable.
    """
    rng = random.Random(seed)
    values: list[float] = []
    out_of_range = 0

    for _ in range(samples):
        # Always draw every variate, even when frozen, so that freezing one
        # input does not shift the stream the others see.
        t_draw = temperature.draw(rng)
        ns_jitter = rng.gauss(0.0, 1.0)
        n_draw = number_per_cm3.draw(rng)
        d_draw = median_diameter_um.draw(rng)

        temp = temperature.central if freeze == "temperature" else t_draw
        number = number_per_cm3.central if freeze == "number" else n_draw
        diameter = median_diameter_um.central if freeze == "diameter" else d_draw

        est = evaluate(param, temp)
        if est.value is None or est.sigma_log10 is None:
            out_of_range += 1
            continue
        ns = est.value
        if freeze != "ns" and est.sigma_log10 > 0:
            ns *= 10.0 ** (ns_jitter * est.sigma_log10)

        values.append(
            _inp_per_litre(ns, number * 1e6, diameter * 1e-6, geometric_sd, n_bins)
        )
    return values, out_of_range


def _log_variance(values: list[float]) -> float:
    positive = [math.log10(v) for v in values if v > 0]
    if len(positive) < 2:
        return 0.0
    mean = sum(positive) / len(positive)
    return sum((v - mean) ** 2 for v in positive) / (len(positive) - 1)


def propagate_inp(
    param: Parameterization,
    *,
    temperature_c: float,
    number_per_cm3: float,
    median_diameter_um: float,
    geometric_sd: float = 1.9,
    temperature_sigma_k: float = 0.5,
    number_relative_sigma: float = 0.30,
    diameter_relative_sigma: float = 0.10,
    threshold_per_litre: float | None = None,
    samples: int = DEFAULT_SAMPLES,
    seed: int = DEFAULT_SEED,
    n_bins: int = DEFAULT_BINS,
) -> MonteCarloResult:
    """Sample n_INP for one aerosol mode with uncertain inputs.

    Deterministic given the seed: the same call always produces the same
    numbers, which is what makes a Monte Carlo result quotable.
    """
    if param.quantity != "ns":
        raise ValueError(
            f"{param.id} is a rate coefficient; an INP concentration needs ns(T)"
        )
    if samples < 100:
        raise ValueError("use at least 100 samples for a meaningful distribution")
    if geometric_sd <= 1.0:
        raise ValueError("geometric_sd must exceed 1")

    temperature = Uncertain(temperature_c, temperature_sigma_k, "normal")
    number = Uncertain(number_per_cm3, number_relative_sigma)
    diameter = Uncertain(median_diameter_um, diameter_relative_sigma)

    values, out_of_range = _run_samples(
        param,
        temperature=temperature,
        number_per_cm3=number,
        median_diameter_um=diameter,
        geometric_sd=geometric_sd,
        samples=samples,
        seed=seed,
        n_bins=n_bins,
    )

    central = evaluate(param, temperature_c)
    result = MonteCarloResult(
        parameterization_id=param.id,
        citation=param.as_dict()["citation"],
        temperature_c=temperature_c,
        threshold_per_litre=threshold_per_litre,
        samples_requested=samples,
        samples_usable=len(values),
        seed=seed,
        values=values,
        out_of_range_fraction=out_of_range / samples,
        sigma_assumed=central.sigma_assumed,
        ns_sigma_used=central.sigma_log10 or 0.0,
    )

    # Variance decomposition under common random numbers.
    total_variance = _log_variance(values)
    if total_variance > 0:
        for name, key, varies in (
            ("ns(T) parameterization", "ns", (central.sigma_log10 or 0) > 0),
            ("temperature", "temperature", temperature.varies),
            ("aerosol number", "number", number.varies),
            ("median diameter", "diameter", diameter.varies),
        ):
            if not varies:
                continue
            frozen, _ = _run_samples(
                param,
                temperature=temperature,
                number_per_cm3=number,
                median_diameter_um=diameter,
                geometric_sd=geometric_sd,
                samples=samples,
                seed=seed,
                n_bins=n_bins,
                freeze=key,
            )
            reduced = _log_variance(frozen)
            share = max(0.0, (total_variance - reduced) / total_variance)
            result.variance_share[name] = share

    if result.out_of_range_fraction > 0.05:
        result.notes.append(
            f"{result.out_of_range_fraction:.0%} of temperature draws fell outside "
            f"the fitted range [{param.t_min_c:g}, {param.t_max_c:g}] °C and were "
            "discarded; the reported distribution is conditioned on being in "
            "range and is biased towards the interior"
        )
    if result.samples_usable < MIN_USABLE_FRACTION * samples:
        result.notes.append(
            "fewer than half the samples were usable: move away from the edge of "
            "the fitted range, or reduce the temperature uncertainty"
        )
    if central.sigma_assumed:
        result.notes.append(
            "the ns uncertainty here is the documented substitute, not a value "
            "the source states, so this band inherits that assumption"
        )
    result.notes.append(
        "inputs are drawn independently and only the uncertainties listed are "
        "propagated; structural error - the fit being wrong, or the wrong "
        "nucleation mode - is not represented and is usually larger"
    )
    return result

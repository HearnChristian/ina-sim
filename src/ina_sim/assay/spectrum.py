"""Invert a droplet-freezing run to ns(T), with the uncertainty it deserves.

The inversion itself is one line of Vali (1971). Everything else here exists
because a bare ns value from a droplet assay is not a measurement yet:

**Counting uncertainty.** A frozen fraction is a binomial proportion from a
finite number of droplets. The interval is Wilson's score interval rather than
the textbook normal approximation, because the normal one collapses to zero
width exactly where droplet assays spend most of their range - at f near 0 and
near 1 - and would report false precision there.

**One-sided points.** f = 0 and f = 1 have no central ns (the inversion needs
0 < f < 1), but they are not useless: they bound ns from one side. They are
reported as limits instead of being dropped.

**Dynamic range.** An assay with N droplets each carrying area A can only
resolve ns between about -ln(1 - 1/N)/A (one droplet frozen) and ln(N)/A (one
droplet unfrozen). Points outside that window are counting artefacts of the
experiment size, not properties of the sample, and are flagged.

This module reports uncertainty from droplet counting only. Temperature
calibration error and surface-area error are usually larger and are NOT
propagated here; see the caveat printed with every spectrum.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ina_sim.assay.ingest import RawAssay
from ina_sim.physics.ns import Parameterization, evaluate, load_parameterizations

# 95% two-sided normal quantile, used for the Wilson score interval.
Z_95 = 1.959963984540054


def wilson_interval(
    n_success: int, n_total: int, *, z: float = Z_95
) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Chosen over the Wald interval because it stays inside [0, 1] and keeps a
    sensible width at f = 0 and f = 1, which is exactly where a droplet-freezing
    curve begins and ends.
    """
    if n_total <= 0:
        raise ValueError("n_total must be positive")
    if not 0 <= n_success <= n_total:
        raise ValueError("n_success must be within [0, n_total]")
    n = float(n_total)
    p = n_success / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    low, high = max(0.0, centre - half), min(1.0, centre + half)
    # The interval is exactly closed at the ends; rounding leaves it a few
    # ulps short, which would turn a saturated point into a finite ns bound.
    if n_success == 0:
        low = 0.0
    if n_success == n_total:
        high = 1.0
    return low, high


def _ns_from_fraction(fraction: float, area_m2: float) -> float | None:
    """ns = -ln(1 - f) / A, or None where that is not defined."""
    if fraction <= 0.0:
        return None
    if fraction >= 1.0:
        return None
    return -math.log(1.0 - fraction) / area_m2


@dataclass(frozen=True)
class SpectrumPoint:
    temperature_c: float
    n_frozen: int
    n_total: int
    frozen_fraction: float
    frozen_fraction_low: float
    frozen_fraction_high: float
    area_m2: float
    ns_m2: float | None
    ns_low_m2: float | None
    ns_high_m2: float | None
    limit: str | None  # None | "upper" | "lower"
    within_dynamic_range: bool
    note: str | None = None

    @property
    def log10_ns(self) -> float | None:
        if self.ns_m2 is None or self.ns_m2 <= 0:
            return None
        return math.log10(self.ns_m2)

    def as_dict(self) -> dict[str, Any]:
        return {
            "T_c": round(self.temperature_c, 4),
            "n_frozen": self.n_frozen,
            "n_total": self.n_total,
            "frozen_fraction": round(self.frozen_fraction, 6),
            "frozen_fraction_low": round(self.frozen_fraction_low, 6),
            "frozen_fraction_high": round(self.frozen_fraction_high, 6),
            "ns_m2": self.ns_m2,
            "ns_low_m2": self.ns_low_m2,
            "ns_high_m2": self.ns_high_m2,
            "log10_ns": None if self.log10_ns is None else round(self.log10_ns, 4),
            "limit": self.limit,
            "within_dynamic_range": self.within_dynamic_range,
            "note": self.note,
        }


@dataclass(frozen=True)
class Spectrum:
    points: tuple[SpectrumPoint, ...]
    area_m2: float
    area_route: str
    area_basis: str
    confidence: float
    ns_resolvable_min_m2: float
    ns_resolvable_max_m2: float
    metadata: dict[str, Any]
    source_path: str | None
    source_sha256: str | None

    @property
    def usable(self) -> tuple[SpectrumPoint, ...]:
        """Points with a central ns value inside the assay's dynamic range."""
        return tuple(
            p for p in self.points if p.ns_m2 is not None and p.within_dynamic_range
        )

    def temperature_span_c(self) -> tuple[float, float] | None:
        usable = self.usable
        if not usable:
            return None
        temps = [p.temperature_c for p in usable]
        return min(temps), max(temps)

    def t50_c(self) -> float | None:
        """Measured median freezing temperature, by linear interpolation."""
        ordered = sorted(self.points, key=lambda p: -p.temperature_c)
        previous = None
        for point in ordered:
            if point.frozen_fraction >= 0.5:
                if previous is None:
                    return point.temperature_c
                span = point.frozen_fraction - previous.frozen_fraction
                if span <= 0:
                    return point.temperature_c
                weight = (0.5 - previous.frozen_fraction) / span
                return round(
                    previous.temperature_c
                    + weight * (point.temperature_c - previous.temperature_c),
                    4,
                )
            previous = point
        return None

    def as_dict(self) -> dict[str, Any]:
        span = self.temperature_span_c()
        return {
            "source": {"path": self.source_path, "sha256": self.source_sha256},
            "metadata": self.metadata,
            "droplet_surface_area_m2": self.area_m2,
            "area_route": self.area_route,
            "area_basis": self.area_basis,
            "confidence": self.confidence,
            "dynamic_range_ns_m2": [
                self.ns_resolvable_min_m2,
                self.ns_resolvable_max_m2,
            ],
            "n_points": len(self.points),
            "n_usable": len(self.usable),
            "usable_T_span_c": list(span) if span else None,
            "t50_c": self.t50_c(),
            "uncertainty_note": (
                "bands are droplet-counting (binomial) uncertainty only, at "
                f"{self.confidence:.0%} confidence via the Wilson score interval. "
                "Temperature calibration and surface-area uncertainty are not "
                "propagated and are usually larger."
            ),
            "points": [p.as_dict() for p in self.points],
        }

    def to_csv(self) -> str:
        header = (
            "T_c,n_frozen,n_total,frozen_fraction,frozen_fraction_low,"
            "frozen_fraction_high,ns_m2,ns_low_m2,ns_high_m2,log10_ns,limit,"
            "within_dynamic_range\n"
        )
        rows = []
        for p in self.points:
            rows.append(
                ",".join(
                    [
                        f"{p.temperature_c:g}",
                        str(p.n_frozen),
                        str(p.n_total),
                        f"{p.frozen_fraction:.6f}",
                        f"{p.frozen_fraction_low:.6f}",
                        f"{p.frozen_fraction_high:.6f}",
                        "" if p.ns_m2 is None else f"{p.ns_m2:.6e}",
                        "" if p.ns_low_m2 is None else f"{p.ns_low_m2:.6e}",
                        "" if p.ns_high_m2 is None else f"{p.ns_high_m2:.6e}",
                        "" if p.log10_ns is None else f"{p.log10_ns:.4f}",
                        p.limit or "",
                        "yes" if p.within_dynamic_range else "no",
                    ]
                )
            )
        return header + "\n".join(rows) + "\n"


def build_spectrum(assay: RawAssay, *, confidence: float = 0.95) -> Spectrum:
    """Invert every reading to ns(T) with a counting-uncertainty band."""
    if not 0.5 < confidence < 1.0:
        raise ValueError("confidence must be between 0.5 and 1")
    # Two-sided normal quantile for the requested confidence, by bisection on
    # the error function so the module keeps its stdlib-only promise.
    z = _normal_quantile(0.5 + confidence / 2.0)

    default_area, route = assay.area_per_droplet_m2()

    points: list[SpectrumPoint] = []
    for reading in assay.readings:
        area = reading.surface_area_m2 or default_area
        fraction = reading.n_frozen / reading.n_total
        f_low, f_high = wilson_interval(reading.n_frozen, reading.n_total, z=z)

        ns = _ns_from_fraction(fraction, area)
        ns_low = _ns_from_fraction(f_low, area)
        ns_high = _ns_from_fraction(f_high, area)

        limit: str | None = None
        note: str | None = None
        if reading.n_frozen == 0:
            limit = "upper"
            note = (
                "no droplet froze: ns is bounded above only, at this "
                "confidence level"
            )
        elif reading.n_frozen == reading.n_total:
            limit = "lower"
            note = (
                "every droplet froze: ns is bounded below only; the assay is "
                "saturated and cannot see higher site densities"
            )

        ns_min = -math.log1p(-1.0 / reading.n_total) / area
        ns_max = math.log(reading.n_total) / area
        within = ns is not None and ns_min <= ns <= ns_max
        if ns is not None and not within:
            note = (
                "outside the resolvable window for "
                f"{reading.n_total} droplets: this reflects the size of the "
                "experiment, not the sample"
            )

        points.append(
            SpectrumPoint(
                temperature_c=reading.temperature_c,
                n_frozen=reading.n_frozen,
                n_total=reading.n_total,
                frozen_fraction=fraction,
                frozen_fraction_low=f_low,
                frozen_fraction_high=f_high,
                area_m2=area,
                ns_m2=ns,
                ns_low_m2=ns_low,
                ns_high_m2=ns_high,
                limit=limit,
                within_dynamic_range=within,
                note=note,
            )
        )

    n_max = max(r.n_total for r in assay.readings)
    return Spectrum(
        points=tuple(points),
        area_m2=default_area,
        area_route=route,
        area_basis=assay.metadata.area_basis,
        confidence=confidence,
        ns_resolvable_min_m2=-math.log1p(-1.0 / n_max) / default_area,
        ns_resolvable_max_m2=math.log(n_max) / default_area,
        metadata=assay.metadata.as_dict(),
        source_path=str(assay.path) if assay.path else None,
        source_sha256=assay.file_sha256,
    )


def _normal_quantile(p: float) -> float:
    """Inverse standard normal CDF via bisection on math.erf."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    lo, hi = -10.0, 10.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        cdf = 0.5 * (1.0 + math.erf(mid / math.sqrt(2.0)))
        if cdf < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


@dataclass(frozen=True)
class Comparison:
    parameterization_id: str
    material: str
    citation: str
    n_compared: int
    rmse_log10: float | None
    bias_log10: float | None
    max_abs_residual_log10: float | None
    coverage_fraction: float | None
    sigma_log10: float | None
    verdict: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "parameterization": self.parameterization_id,
            "material": self.material,
            "citation": self.citation,
            "n_compared": self.n_compared,
            "rmse_log10": None if self.rmse_log10 is None else round(self.rmse_log10, 3),
            "bias_log10": None if self.bias_log10 is None else round(self.bias_log10, 3),
            "max_abs_residual_log10": (
                None
                if self.max_abs_residual_log10 is None
                else round(self.max_abs_residual_log10, 3)
            ),
            "coverage_fraction": (
                None if self.coverage_fraction is None else round(self.coverage_fraction, 3)
            ),
            "sigma_log10": self.sigma_log10,
            "verdict": self.verdict,
        }


def _verdict(bias: float, rmse: float, coverage: float, sigma: float | None) -> str:
    if sigma and coverage >= 0.68 and abs(bias) <= sigma:
        return "consistent with this fit"
    if sigma and abs(bias) > 2 * sigma:
        direction = "more" if bias > 0 else "less"
        return f"sample is {direction} active than this fit by >2 sigma"
    if rmse > 2.0:
        return "scatter too large to call either way"
    return "marginal: outside 1 sigma but within 2"


def compare_to_registry(
    spectrum: Spectrum,
    *,
    parameterizations: dict[str, Parameterization] | None = None,
) -> list[Comparison]:
    """Compare a measured spectrum against every applicable published fit.

    Only singular ns parameterizations on the SAME surface-area basis are
    considered. Comparing a BET-derived measurement against a geometric fit is
    the mistake this whole layer exists to prevent, so those are excluded rather
    than reported with a caveat.
    """
    params = parameterizations or load_parameterizations()
    usable = spectrum.usable
    out: list[Comparison] = []

    for param in params.values():
        if param.quantity != "ns":
            continue
        if param.area_basis != spectrum.area_basis:
            continue

        residuals: list[float] = []
        inside = 0
        sigma = None
        for point in usable:
            est = evaluate(param, point.temperature_c)
            if est.value is None or est.log10_value is None:
                continue
            sigma = est.sigma_log10
            measured = point.log10_ns
            if measured is None:
                continue
            residual = measured - est.log10_value
            residuals.append(residual)
            if sigma is not None and abs(residual) <= sigma:
                inside += 1

        if not residuals:
            out.append(
                Comparison(
                    parameterization_id=param.id,
                    material=param.material,
                    citation=param.as_dict()["citation"],
                    n_compared=0,
                    rmse_log10=None,
                    bias_log10=None,
                    max_abs_residual_log10=None,
                    coverage_fraction=None,
                    sigma_log10=param.sigma_log10,
                    verdict="no overlap between this run and the fitted range",
                )
            )
            continue

        n = len(residuals)
        bias = sum(residuals) / n
        rmse = math.sqrt(sum(r * r for r in residuals) / n)
        coverage = inside / n
        out.append(
            Comparison(
                parameterization_id=param.id,
                material=param.material,
                citation=param.as_dict()["citation"],
                n_compared=n,
                rmse_log10=rmse,
                bias_log10=bias,
                max_abs_residual_log10=max(abs(r) for r in residuals),
                coverage_fraction=coverage,
                sigma_log10=sigma,
                verdict=_verdict(bias, rmse, coverage, sigma),
            )
        )

    out.sort(key=lambda c: (c.n_compared == 0, c.rmse_log10 if c.rmse_log10 else 1e9))
    return out

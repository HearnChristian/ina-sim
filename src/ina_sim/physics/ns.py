"""Evaluation of published ice nucleation parameterizations.

This module is deliberately boring: it reads library/parameterizations.yaml,
evaluates the stated equation, and refuses to do anything the source does not
support. In particular it will not

  * return a value outside the temperature range the source fitted, unless the
    caller explicitly asks for extrapolation, and then the result is flagged;
  * hide a missing uncertainty (a substituted default is marked sigma_assumed);
  * let ns values measured on different surface-area bases be compared.

Terminology follows Vali et al. (2015): ns(T) is the ice nucleation active
site density, dimension L^-2; particles that nucleate ice are ice nucleating
particles (INP), not "ice nuclei".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from typing import Any, Literal

import yaml

from ina_sim.references import cite
from ina_sim.units import (
    celsius_to_kelvin,
    ns_cm2_to_m2,
)

Quantity = Literal["ns", "j_het", "j_hom"]

SINGULAR_FORMS = {"log10_poly_c", "log10_linear_c", "ln_linear_c"}
RATE_FORMS = {"ln_J_linear_k"}

# Above this the "site density" would exceed a plausible number of surface
# molecules per unit area (~10^19 m^-2); flag rather than silently accept.
MAX_PLAUSIBLE_NS_M2 = 1e19


@dataclass(frozen=True)
class Parameterization:
    """One row of library/parameterizations.yaml."""

    id: str
    material: str
    status: str  # published | derived
    kind: str  # singular | stochastic
    mode: str  # immersion | deposition | contact | homogeneous
    form: str
    coefficients: tuple[float, ...]
    units: str
    area_basis: str  # BET | geometric | volume
    t_min_c: float
    t_max_c: float
    reference: str
    sigma_log10: float | None = None
    applies_to: tuple[str, ...] = ()
    quote: str | None = None
    caveat: str | None = None
    derivation: str | None = None
    dataset: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def quantity(self) -> Quantity:
        if self.form in RATE_FORMS:
            return "j_hom" if self.area_basis == "volume" else "j_het"
        return "ns"

    def covers(self, temp_c: float) -> bool:
        return self.t_min_c <= temp_c <= self.t_max_c

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "material": self.material,
            "status": self.status,
            "kind": self.kind,
            "mode": self.mode,
            "quantity": self.quantity,
            "units": self.units,
            "area_basis": self.area_basis,
            "valid_t_c": [self.t_min_c, self.t_max_c],
            "sigma_log10": self.sigma_log10,
            "reference": self.reference,
            "citation": cite(self.reference),
            "applies_to": list(self.applies_to),
            "quote": self.quote,
            "caveat": self.caveat,
            "derivation": self.derivation,
        }


@dataclass(frozen=True)
class Estimate:
    """Result of evaluating one parameterization at one temperature."""

    parameterization_id: str
    material: str
    quantity: Quantity
    temperature_c: float
    value: float | None  # ns in m^-2, or J in cm^-2 s^-1 / cm^-3 s^-1
    units: str
    log10_value: float | None
    low: float | None
    high: float | None
    sigma_log10: float | None
    sigma_assumed: bool
    area_basis: str
    status: str
    mode: str
    in_range: bool
    extrapolated: bool
    reference: str
    citation: str
    notes: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return self.value is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "parameterization": self.parameterization_id,
            "material": self.material,
            "quantity": self.quantity,
            "T_c": round(self.temperature_c, 4),
            "value": self.value,
            "units": self.units,
            "log10_value": None if self.log10_value is None else round(self.log10_value, 3),
            "low": self.low,
            "high": self.high,
            "sigma_log10": self.sigma_log10,
            "sigma_assumed": self.sigma_assumed,
            "area_basis": self.area_basis,
            "status": self.status,
            "mode": self.mode,
            "in_range": self.in_range,
            "extrapolated": self.extrapolated,
            "reference": self.reference,
            "citation": self.citation,
            "notes": list(self.notes),
        }


class AreaBasisError(ValueError):
    """Raised when values on incompatible surface-area bases would be mixed."""


@lru_cache(maxsize=1)
def _load_raw() -> dict[str, Any]:
    ref = resources.files("ina_sim.library").joinpath("parameterizations.yaml")
    with ref.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def default_sigma() -> tuple[float, str]:
    raw = _load_raw()
    return (
        float(raw.get("default_sigma_log10", 1.0)),
        str(raw.get("default_sigma_reference", "")),
    )


@lru_cache(maxsize=1)
def load_parameterizations() -> dict[str, Parameterization]:
    raw = _load_raw()
    out: dict[str, Parameterization] = {}
    for row in raw.get("parameterizations") or []:
        known = {
            "id",
            "applies_to",
            "material",
            "status",
            "kind",
            "mode",
            "form",
            "coefficients",
            "ns_units",
            "area_basis",
            "t_min_c",
            "t_max_c",
            "sigma_log10",
            "reference",
            "quote",
            "caveat",
            "derivation",
            "dataset",
        }
        param = Parameterization(
            id=str(row["id"]),
            material=str(row.get("material", "")),
            status=str(row.get("status", "published")),
            kind=str(row.get("kind", "singular")),
            mode=str(row.get("mode", "immersion")),
            form=str(row["form"]),
            coefficients=tuple(float(c) for c in row["coefficients"]),
            units=str(row["ns_units"]),
            area_basis=str(row.get("area_basis", "unknown")),
            t_min_c=float(row["t_min_c"]),
            t_max_c=float(row["t_max_c"]),
            reference=str(row["reference"]),
            sigma_log10=(
                None if row.get("sigma_log10") is None else float(row["sigma_log10"])
            ),
            applies_to=tuple(str(a) for a in (row.get("applies_to") or ())),
            quote=row.get("quote"),
            caveat=row.get("caveat"),
            derivation=row.get("derivation"),
            dataset=row.get("dataset"),
            extra={k: v for k, v in row.items() if k not in known},
        )
        if param.id in out:
            raise ValueError(f"duplicate parameterization id {param.id!r}")
        out[param.id] = param
    return out


def get_parameterization(param_id: str) -> Parameterization:
    params = load_parameterizations()
    if param_id not in params:
        raise KeyError(f"unknown parameterization {param_id!r}")
    return params[param_id]


def parameterizations_for(candidate_id: str) -> list[Parameterization]:
    """Parameterizations that describe a library candidate, if any."""
    return [
        p for p in load_parameterizations().values() if candidate_id in p.applies_to
    ]


def _evaluate_log10(param: Parameterization, temp_c: float) -> float:
    """Return log10 of the parameterized quantity in the source's own units."""
    coeffs = param.coefficients
    if param.form == "log10_poly_c":
        return sum(c * temp_c**i for i, c in enumerate(coeffs))
    if param.form == "log10_linear_c":
        return coeffs[0] + coeffs[1] * temp_c
    if param.form == "ln_linear_c":
        return (coeffs[0] + coeffs[1] * temp_c) / math.log(10.0)
    if param.form == "ln_J_linear_k":
        temp_k = celsius_to_kelvin(temp_c)
        return (coeffs[0] + coeffs[1] * temp_k) / math.log(10.0)
    raise ValueError(f"unsupported form {param.form!r} in {param.id!r}")


def _to_si(param: Parameterization, value: float) -> tuple[float, str]:
    """Convert the source's units to the unit this package reports."""
    if param.units == "cm^-2":
        return ns_cm2_to_m2(value), "m^-2"
    # Rate coefficients are kept in the source's CGS units: that is how every
    # paper quotes them, and converting invites silent factor-10^4 errors.
    return value, param.units


def evaluate(
    param: Parameterization,
    temp_c: float,
    *,
    allow_extrapolation: bool = False,
) -> Estimate:
    """Evaluate one parameterization, refusing to extrapolate by default."""
    notes: list[str] = []
    in_range = param.covers(temp_c)
    extrapolated = False

    sigma = param.sigma_log10
    sigma_assumed = False
    if sigma is None:
        sigma, sigma_ref = default_sigma()
        sigma_assumed = True
        notes.append(
            f"source states no uncertainty; using {sigma} decades from "
            f"{cite(sigma_ref)} as a documented stand-in"
        )

    if param.status == "derived":
        notes.append("derived in-repo from tabulated measurements, not a published fit")
    if param.caveat:
        notes.append(" ".join(str(param.caveat).split()))

    if not in_range:
        if not allow_extrapolation:
            notes.append(
                f"T={temp_c:g} C is outside the fitted range "
                f"[{param.t_min_c:g}, {param.t_max_c:g}] C; no value returned"
            )
            return Estimate(
                parameterization_id=param.id,
                material=param.material,
                quantity=param.quantity,
                temperature_c=temp_c,
                value=None,
                units=param.units if param.units != "cm^-2" else "m^-2",
                log10_value=None,
                low=None,
                high=None,
                sigma_log10=sigma,
                sigma_assumed=sigma_assumed,
                area_basis=param.area_basis,
                status=param.status,
                mode=param.mode,
                in_range=False,
                extrapolated=False,
                reference=param.reference,
                citation=cite(param.reference),
                notes=tuple(notes),
            )
        extrapolated = True
        notes.append(
            f"EXTRAPOLATED beyond [{param.t_min_c:g}, {param.t_max_c:g}] C — "
            "the source does not support this value"
        )

    log10_src = _evaluate_log10(param, temp_c)
    if not math.isfinite(log10_src):
        notes.append("equation did not evaluate to a finite number")
        value: float | None = None
        log10_si: float | None = None
        low = high = None
    else:
        raw = 10.0**log10_src
        value, out_units = _to_si(param, raw)
        log10_si = math.log10(value) if value > 0 else None
        low = 10.0 ** (log10_si - sigma) if log10_si is not None else None
        high = 10.0 ** (log10_si + sigma) if log10_si is not None else None
        if param.quantity == "ns" and value > MAX_PLAUSIBLE_NS_M2:
            notes.append(
                f"ns exceeds {MAX_PLAUSIBLE_NS_M2:.0e} m^-2, more sites than a "
                "monolayer of surface molecules — treat as saturated"
            )

    units_out = "m^-2" if param.units == "cm^-2" else param.units
    return Estimate(
        parameterization_id=param.id,
        material=param.material,
        quantity=param.quantity,
        temperature_c=temp_c,
        value=value,
        units=units_out,
        log10_value=log10_si,
        low=low,
        high=high,
        sigma_log10=sigma,
        sigma_assumed=sigma_assumed,
        area_basis=param.area_basis,
        status=param.status,
        mode=param.mode,
        in_range=in_range,
        extrapolated=extrapolated,
        reference=param.reference,
        citation=cite(param.reference),
        notes=tuple(notes),
    )


def evaluate_for_candidate(
    candidate_id: str,
    temp_c: float,
    *,
    mode: str = "immersion",
    allow_extrapolation: bool = False,
) -> Estimate | None:
    """Best available estimate for a library candidate, or None if unmeasured.

    Returning None is a real answer: most of the library has no published
    parameterization, and saying so is more useful than a number.
    """
    params = parameterizations_for(candidate_id)
    if not params:
        return None
    preferred = [p for p in params if p.mode == mode] or params
    in_range = [p for p in preferred if p.covers(temp_c)]
    chosen = (in_range or preferred)[0]
    return evaluate(chosen, temp_c, allow_extrapolation=allow_extrapolation)


def assert_comparable(estimates: list[Estimate]) -> None:
    """Guard against ranking ns values that are not on the same footing.

    BET and geometric surface areas differ by more than an order of magnitude
    for clays (Hiranuma et al. 2015), and a volume-based rate coefficient is not
    an area density at all, so ordering across bases is meaningless.
    """
    usable = [e for e in estimates if e.available]
    if len(usable) < 2:
        return
    quantities = {e.quantity for e in usable}
    if len(quantities) > 1:
        raise AreaBasisError(
            f"cannot compare different quantities: {sorted(quantities)}"
        )
    bases = {e.area_basis for e in usable}
    if len(bases) > 1:
        raise AreaBasisError(
            "cannot compare ns values on different surface-area bases: "
            f"{sorted(bases)}. BET and geometric areas differ by more than an "
            "order of magnitude for fine-grained samples (Hiranuma et al. 2015)."
        )


def registry_summary() -> dict[str, Any]:
    """Machine-readable inventory of what this build can support empirically."""
    params = load_parameterizations()
    sigma, sigma_ref = default_sigma()
    return {
        "count": len(params),
        "published": sum(1 for p in params.values() if p.status == "published"),
        "derived": sum(1 for p in params.values() if p.status == "derived"),
        "default_sigma_log10": sigma,
        "default_sigma_reference": sigma_ref,
        "parameterizations": [p.as_dict() for p in params.values()],
    }

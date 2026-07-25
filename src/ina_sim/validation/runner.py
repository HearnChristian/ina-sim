"""Run the validation anchors and report residuals.

`ina-sim validate` is the answer to "why should I believe any of this?".
It re-derives, at run time, whether the shipped parameterizations still
reproduce the published claims in validation/anchors.yaml, and reports the
residual for each one in the natural unit (decades of ns, or degrees).

A failing anchor is a build failure, not a warning: tests/test_validation.py
runs this suite, so a coefficient typo or a unit slip cannot reach a demo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from typing import Any

import yaml

from ina_sim.physics.freezing import stochastic_freezing_curve
from ina_sim.physics.ns import evaluate, get_parameterization
from ina_sim.references import cite
from ina_sim.units import KELVIN_OFFSET, sphere_surface_area_m2, sphere_volume_m3

DATASET_PACKAGE = "ina_sim.validation.datasets"


@dataclass(frozen=True)
class AnchorResult:
    id: str
    kind: str
    status: str  # pass | fail | skip
    detail: str
    residual: float | None
    tolerance: float | None
    unit: str
    reference: str
    citation: str
    claim: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "detail": self.detail,
            "residual": None if self.residual is None else round(self.residual, 4),
            "tolerance": self.tolerance,
            "unit": self.unit,
            "reference": self.reference,
            "citation": self.citation,
            "claim": " ".join(self.claim.split()),
        }


@dataclass
class ValidationReport:
    results: list[AnchorResult] = field(default_factory=list)

    @property
    def n_pass(self) -> int:
        return sum(1 for r in self.results if r.status == "pass")

    @property
    def n_fail(self) -> int:
        return sum(1 for r in self.results if r.status == "fail")

    @property
    def n_skip(self) -> int:
        return sum(1 for r in self.results if r.status == "skip")

    @property
    def ok(self) -> bool:
        return self.n_fail == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "pass": self.n_pass,
                "fail": self.n_fail,
                "skip": self.n_skip,
                "ok": self.ok,
            },
            "anchors": [r.as_dict() for r in self.results],
        }


@lru_cache(maxsize=1)
def load_anchors() -> list[dict[str, Any]]:
    ref = resources.files("ina_sim.validation").joinpath("anchors.yaml")
    with ref.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return list(raw.get("anchors") or [])


@lru_cache(maxsize=4)
def load_dataset(filename: str) -> dict[str, Any]:
    ref = resources.files(DATASET_PACKAGE).joinpath(filename)
    with ref.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _check_value_log10(anchor: dict[str, Any]) -> AnchorResult:
    param = get_parameterization(anchor["parameterization"])
    est = evaluate(param, float(anchor["temperature_c"]))
    tol = float(anchor["tolerance_log10"])
    expected = float(anchor["expected_log10"])
    common = dict(
        id=anchor["id"],
        kind=anchor["kind"],
        tolerance=tol,
        unit="log10 decades",
        reference=anchor["reference"],
        citation=cite(anchor["reference"]),
        claim=anchor.get("claim", ""),
    )
    if est.value is None or est.log10_value is None:
        return AnchorResult(
            status="skip",
            detail=f"{param.id} returned no value at {anchor['temperature_c']} C",
            residual=None,
            **common,
        )
    residual = est.log10_value - expected
    ok = abs(residual) <= tol
    return AnchorResult(
        status="pass" if ok else "fail",
        detail=(
            f"log10({est.quantity}) = {est.log10_value:.3f} vs claimed "
            f"{expected:.3f} at T = {anchor['temperature_c']} C "
            f"({float(anchor['temperature_c']) + KELVIN_OFFSET:.1f} K), "
            f"residual {residual:+.3f} decades (tolerance {tol})"
        ),
        residual=residual,
        **common,
    )


def _check_ordering(anchor: dict[str, Any]) -> AnchorResult:
    ids = list(anchor["parameterizations"])
    temps = [float(t) for t in anchor["temperatures_c"]]
    common = dict(
        id=anchor["id"],
        kind=anchor["kind"],
        tolerance=None,
        unit="ordering",
        reference=anchor["reference"],
        citation=cite(anchor["reference"]),
        claim=anchor.get("claim", ""),
    )
    violations: list[str] = []
    compared = 0
    for temp in temps:
        values: list[tuple[str, float]] = []
        for pid in ids:
            est = evaluate(get_parameterization(pid), temp)
            if est.log10_value is not None:
                values.append((pid, est.log10_value))
        for (id_a, val_a), (id_b, val_b) in zip(values, values[1:]):
            compared += 1
            if not val_a > val_b:
                violations.append(
                    f"{temp:g}C: {id_a} ({val_a:.2f}) should exceed {id_b} ({val_b:.2f})"
                )
    if compared == 0:
        return AnchorResult(
            status="skip",
            detail="no temperatures fell inside the shared validity ranges",
            residual=None,
            **common,
        )
    return AnchorResult(
        status="pass" if not violations else "fail",
        detail=(
            f"{compared} pairwise comparisons across {len(temps)} temperatures, "
            f"{len(violations)} violations"
            + ("; " + "; ".join(violations) if violations else "")
        ),
        residual=float(len(violations)),
        **common,
    )


def _check_stochastic_t50(anchor: dict[str, Any]) -> AnchorResult:
    param = get_parameterization(anchor["parameterization"])
    diameter_m = float(anchor["droplet_diameter_um"]) * 1e-6
    lo = float(anchor["expected_min_c"])
    hi = float(anchor["expected_max_c"])
    common = dict(
        id=anchor["id"],
        kind=anchor["kind"],
        tolerance=None,
        unit="degrees C",
        reference=anchor["reference"],
        citation=cite(anchor["reference"]),
        claim=anchor.get("claim", ""),
    )
    curve = stochastic_freezing_curve(
        None,
        particle_area_m2=0.0,
        droplet_volume_m3=sphere_volume_m3(diameter_m),
        hom_param=param,
        cooling_rate_k_per_min=float(anchor.get("cooling_rate_k_per_min", 1.0)),
        t_start_c=param.t_max_c,
        t_end_c=param.t_min_c,
        step_c=0.01,
    )
    t50 = next((p["T_c"] for p in curve if p["frozen_fraction"] >= 0.5), None)
    if t50 is None:
        return AnchorResult(
            status="fail",
            detail=(
                "droplets never reached 50 percent frozen inside the rate "
                "coefficient's validity range"
            ),
            residual=None,
            **common,
        )
    ok = lo <= t50 <= hi
    return AnchorResult(
        status="pass" if ok else "fail",
        detail=(
            f"T50 = {t50:.2f} C for a {anchor['droplet_diameter_um']} um droplet "
            f"cooled at {anchor.get('cooling_rate_k_per_min', 1.0)} K/min; "
            f"expected window [{lo}, {hi}] C"
        ),
        residual=0.0 if ok else min(abs(t50 - lo), abs(t50 - hi)),
        **common,
    )


def _check_band_coverage(anchor: dict[str, Any]) -> AnchorResult:
    param = get_parameterization(anchor["parameterization"])
    data = load_dataset(anchor["dataset"])
    k = float(anchor.get("sigma_multiplier", 1.0))
    min_coverage = float(anchor["min_coverage"])
    common = dict(
        id=anchor["id"],
        kind=anchor["kind"],
        tolerance=min_coverage,
        unit="fraction covered",
        reference=anchor["reference"],
        citation=cite(anchor["reference"]),
        claim=anchor.get("claim", ""),
    )
    sigma = param.sigma_log10
    if sigma is None:
        return AnchorResult(
            status="skip",
            detail=f"{param.id} has no stated sigma to test",
            residual=None,
            **common,
        )

    inside = 0
    total = 0
    worst = 0.0
    for row in data.get("measurements", []):
        if not row.get("use_in_fit", False):
            continue
        frozen = float(row["frozen_fraction"])
        if not 0.0 < frozen < 1.0:
            continue
        area = float(row["particles_per_droplet"]) * sphere_surface_area_m2(
            float(row["diameter_nm"]) * 1e-9
        )
        measured_log10 = math.log10(-math.log(1.0 - frozen) / area)
        temp_c = float(row["temperature_k"]) - KELVIN_OFFSET
        est = evaluate(param, temp_c, allow_extrapolation=True)
        if est.log10_value is None:
            continue
        total += 1
        deviation = abs(measured_log10 - est.log10_value)
        worst = max(worst, deviation)
        if deviation <= k * sigma:
            inside += 1
    if total == 0:
        return AnchorResult(
            status="skip",
            detail="no invertible measurements in the dataset",
            residual=None,
            **common,
        )
    coverage = inside / total
    return AnchorResult(
        status="pass" if coverage >= min_coverage else "fail",
        detail=(
            f"{inside}/{total} measurements inside the {k:g} sigma band "
            f"(+/-{k * sigma:.2f} decades); coverage {coverage:.2%}, "
            f"required {min_coverage:.0%}; largest deviation {worst:.2f} decades"
        ),
        residual=coverage,
        **common,
    )


_CHECKS = {
    "value_log10": _check_value_log10,
    "ordering": _check_ordering,
    "stochastic_t50_window": _check_stochastic_t50,
    "band_coverage": _check_band_coverage,
}


def run_validation(anchors: list[dict[str, Any]] | None = None) -> ValidationReport:
    report = ValidationReport()
    for anchor in anchors if anchors is not None else load_anchors():
        kind = str(anchor.get("kind", ""))
        check = _CHECKS.get(kind)
        if check is None:
            report.results.append(
                AnchorResult(
                    id=str(anchor.get("id", "?")),
                    kind=kind,
                    status="fail",
                    detail=f"unknown anchor kind {kind!r}",
                    residual=None,
                    tolerance=None,
                    unit="",
                    reference=str(anchor.get("reference", "")),
                    citation=cite(str(anchor.get("reference", ""))),
                    claim=str(anchor.get("claim", "")),
                )
            )
            continue
        report.results.append(check(anchor))
    return report


def format_report(report: ValidationReport) -> str:
    lines = ["INA-sim validation against published claims", ""]
    for r in report.results:
        mark = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[r.status]
        lines.append(f"[{mark}] {r.id}  ({r.citation})")
        lines.append(f"       {r.detail}")
    lines.append("")
    lines.append(
        f"{report.n_pass} passed, {report.n_fail} failed, {report.n_skip} skipped"
    )
    if not report.ok:
        lines.append("VALIDATION FAILED - do not quote numbers from this build.")
    return "\n".join(lines)

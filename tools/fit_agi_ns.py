#!/usr/bin/env python3
"""Derive an AgI ns(T) parameterization from Marcolli et al. (2016) Table 1.

AgI is the historical baseline of glaciogenic seeding but, unlike K-feldspar or
desert dust, it has no published INAS parameterization to copy. This script
builds one the only defensible way: invert the published immersion-freezing
measurements with the singular approximation of Vali (1971),

    ns(T) = -ln(1 - f) / (N * pi * d^2)          [m^-2, geometric area basis]

then least-squares fit log10(ns) linearly in T (degrees Celsius).

The scatter is the point, not a nuisance. Run this and read the residual table
before quoting any AgI number: sixty years of AgI experiments do not collapse
onto one surface-area scaling, which is Marcolli et al.'s own conclusion.

Usage:
    python tools/fit_agi_ns.py               # human-readable report
    python tools/fit_agi_ns.py --yaml        # YAML block for parameterizations.yaml
    python tools/fit_agi_ns.py --check       # non-zero exit if the shipped fit drifted
"""

from __future__ import annotations

import argparse
import hashlib
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET = (
    REPO_ROOT
    / "src"
    / "ina_sim"
    / "validation"
    / "datasets"
    / "agi_marcolli2016_table1.yaml"
)
SHIPPED = REPO_ROOT / "src" / "ina_sim" / "library" / "parameterizations.yaml"
SHIPPED_ID = "agi_marcolli2016_derived"

KELVIN_OFFSET = 273.15
# Tolerance when comparing the recomputed fit against the shipped coefficients.
COEFF_TOL = 5e-3


@dataclass(frozen=True)
class Point:
    study: str
    diameter_nm: float
    n_per_droplet: float
    frozen_fraction: float
    temperature_c: float
    ns_m2: float

    @property
    def log10_ns(self) -> float:
        return math.log10(self.ns_m2)


def sphere_area_m2(diameter_nm: float) -> float:
    """Sphere-equivalent geometric surface area of one particle."""
    d_m = diameter_nm * 1e-9
    return math.pi * d_m * d_m


def singular_ns(frozen_fraction: float, n_per_droplet: float, diameter_nm: float) -> float:
    """Vali (1971) singular inversion; returns ns in m^-2."""
    if not 0.0 < frozen_fraction < 1.0:
        raise ValueError("frozen_fraction must be strictly between 0 and 1 to invert")
    area_total = n_per_droplet * sphere_area_m2(diameter_nm)
    if area_total <= 0:
        raise ValueError("total particle surface area must be positive")
    return -math.log(1.0 - frozen_fraction) / area_total


def load_points(path: Path = DATASET) -> tuple[list[Point], list[dict[str, Any]]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    used: list[Point] = []
    skipped: list[dict[str, Any]] = []
    for row in raw["measurements"]:
        if not row.get("use_in_fit", False):
            skipped.append(row)
            continue
        used.append(
            Point(
                study=row["study"],
                diameter_nm=float(row["diameter_nm"]),
                n_per_droplet=float(row["particles_per_droplet"]),
                frozen_fraction=float(row["frozen_fraction"]),
                temperature_c=float(row["temperature_k"]) - KELVIN_OFFSET,
                ns_m2=singular_ns(
                    float(row["frozen_fraction"]),
                    float(row["particles_per_droplet"]),
                    float(row["diameter_nm"]),
                ),
            )
        )
    return used, skipped


def least_squares_line(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Ordinary least squares y = intercept + slope * x, stdlib only."""
    n = len(xs)
    if n < 2:
        raise ValueError("need at least two points to fit a line")
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        raise ValueError("all temperatures identical; slope undefined")
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx
    return mean_y - slope * mean_x, slope


def fit(points: list[Point]) -> dict[str, Any]:
    xs = [p.temperature_c for p in points]
    ys = [p.log10_ns for p in points]
    intercept, slope = least_squares_line(xs, ys)
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    n = len(points)
    # Residual standard deviation with the 2 fitted parameters removed.
    sigma = math.sqrt(sum(r * r for r in residuals) / (n - 2))
    mean_y = sum(ys) / n
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum(r * r for r in residuals)
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {
        "intercept": intercept,
        "slope": slope,
        "sigma_log10": sigma,
        "r_squared": r_squared,
        "n_points": n,
        "t_min_c": min(xs),
        "t_max_c": max(xs),
        "residuals": residuals,
        "max_abs_residual": max(abs(r) for r in residuals),
    }


def dataset_sha256(path: Path = DATASET) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def report(points: list[Point], skipped: list[dict[str, Any]], result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("AgI ns(T) derived from Marcolli et al. (2016) Table 1")
    lines.append(f"dataset: {DATASET.relative_to(REPO_ROOT)}  sha256[:16]={dataset_sha256()}")
    lines.append("inversion: ns = -ln(1-f) / (N * pi * d^2)   [m^-2, geometric area]")
    lines.append("")
    lines.append(
        f"{'study':<10} {'d/nm':>7} {'N/drop':>7} {'f':>5} {'T/C':>7} "
        f"{'log10 ns':>9} {'resid':>7}"
    )
    lines.append("-" * 62)
    ordered = sorted(zip(points, result["residuals"]), key=lambda pr: pr[0].temperature_c)
    for p, r in ordered:
        lines.append(
            f"{p.study:<10} {p.diameter_nm:>7.0f} {p.n_per_droplet:>7.0f} "
            f"{p.frozen_fraction:>5.2f} {p.temperature_c:>7.2f} "
            f"{p.log10_ns:>9.2f} {r:>+7.2f}"
        )
    lines.append("")
    lines.append(
        f"fit: log10(ns[m^-2]) = {result['intercept']:.4f} "
        f"+ ({result['slope']:.4f}) * T[C]"
    )
    lines.append(
        f"     n={result['n_points']}  valid {result['t_min_c']:.2f} to "
        f"{result['t_max_c']:.2f} C  R^2={result['r_squared']:.3f}"
    )
    lines.append(
        f"     residual sigma = {result['sigma_log10']:.2f} decades  "
        f"(max |residual| = {result['max_abs_residual']:.2f} decades)"
    )
    lines.append("")
    lines.append(f"excluded rows: {len(skipped)}")
    for row in skipped:
        reason = " ".join(str(row.get("exclude_reason", "")).split())
        lines.append(
            f"  - {row['study']} {row['diameter_nm']}nm "
            f"f={row['frozen_fraction']}: {reason}"
        )
    lines.append("")
    if result["sigma_log10"] > 1.0:
        lines.append(
            "INTERPRETATION: residual scatter exceeds one order of magnitude, so a "
            "single surface-area scaling does not describe AgI. Marcolli et al. reach "
            "the same conclusion (surface area matters but is 'not the only' factor). "
            "Use this fit as a central estimate with an explicit multi-decade band, "
            "never as a calibrated ns(T)."
        )
    return "\n".join(lines)


def yaml_block(result: dict[str, Any]) -> str:
    block = {
        "id": SHIPPED_ID,
        "applies_to": ["agi"],
        "status": "derived",
        "kind": "singular",
        "mode": "immersion",
        "material": "AgI (compilation of 6 studies, 1962-2016)",
        "form": "log10_linear_c",
        "coefficients": [round(result["intercept"], 4), round(result["slope"], 4)],
        "ns_units": "m^-2",
        "area_basis": "geometric",
        "t_min_c": round(result["t_min_c"], 2),
        "t_max_c": round(result["t_max_c"], 2),
        "sigma_log10": round(result["sigma_log10"], 2),
        "reference": "marcolli2016",
        "derivation": "tools/fit_agi_ns.py",
        "dataset": str(DATASET.relative_to(REPO_ROOT)),
        "dataset_sha256": dataset_sha256(),
        "n_points": result["n_points"],
        "r_squared": round(result["r_squared"], 3),
    }
    return yaml.safe_dump([block], sort_keys=False, allow_unicode=True)


def check_against_shipped(result: dict[str, Any]) -> int:
    shipped = yaml.safe_load(SHIPPED.read_text(encoding="utf-8"))
    entry = next(
        (p for p in shipped.get("parameterizations", []) if p.get("id") == SHIPPED_ID),
        None,
    )
    if entry is None:
        print(f"FAIL: {SHIPPED_ID} not found in {SHIPPED}", file=sys.stderr)
        return 1
    problems: list[str] = []
    want = [result["intercept"], result["slope"]]
    got = [float(c) for c in entry["coefficients"]]
    for name, w, g in zip(("intercept", "slope"), want, got):
        if abs(w - g) > COEFF_TOL:
            problems.append(f"{name}: shipped {g} vs recomputed {w:.4f}")
    if abs(float(entry["sigma_log10"]) - result["sigma_log10"]) > 0.05:
        problems.append(
            f"sigma_log10: shipped {entry['sigma_log10']} vs recomputed "
            f"{result['sigma_log10']:.2f}"
        )
    if entry.get("dataset_sha256") != dataset_sha256():
        problems.append(
            f"dataset hash: shipped {entry.get('dataset_sha256')} vs actual {dataset_sha256()}"
        )
    if problems:
        print("FAIL: shipped AgI fit is out of date:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("Re-run: python tools/fit_agi_ns.py --yaml", file=sys.stderr)
        return 1
    print("OK: shipped AgI fit matches the dataset.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--yaml", action="store_true", help="print the parameterizations.yaml block")
    ap.add_argument("--check", action="store_true", help="verify the shipped fit is current")
    args = ap.parse_args(argv)

    points, skipped = load_points()
    result = fit(points)

    if args.check:
        return check_against_shipped(result)
    if args.yaml:
        print(yaml_block(result))
        return 0
    print(report(points, skipped, result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

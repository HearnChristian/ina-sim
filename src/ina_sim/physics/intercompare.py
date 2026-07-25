"""How much do the published fits disagree with each other?

The single most useful thing you can show someone about ice nucleation
parameterizations is the spread between them. A screen that reports one number
implies a precision the field does not have; putting the available fits side by
side, on a temperature grid, with their own stated uncertainties, shows what is
actually known.

Two rules make the comparison mean something:

  * only fits of the same quantity on the same surface-area basis are placed in
    a group, because a BET ns, a geometric ns and a rate coefficient are three
    different quantities wearing similar symbols;
  * a *conflict* is only possible between fits of the SAME material. Two fits
    of different substances differing by three decades are not disagreeing;
    they are reporting that one mineral nucleates ice better than another. Only
    when two fits share a material_key and their sigma bands fail to overlap is
    the literature actually in conflict, and only then is it flagged.

The spread across a group is still reported, because "how far apart are these
materials" is the question the plot usually gets asked. It is labelled as range
across materials, not as disagreement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ina_sim.physics.ns import Parameterization, evaluate, load_parameterizations


@dataclass(frozen=True)
class GridCell:
    parameterization_id: str
    material_key: str
    log10_value: float | None
    sigma_log10: float | None
    in_range: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "parameterization": self.parameterization_id,
            "material_key": self.material_key,
            "log10_value": None if self.log10_value is None else round(self.log10_value, 3),
            "sigma_log10": self.sigma_log10,
            "in_range": self.in_range,
        }


@dataclass(frozen=True)
class GridRow:
    temperature_c: float
    cells: tuple[GridCell, ...]
    spread_log10: float | None
    widest_pair: tuple[str, str] | None
    conflicts: tuple[tuple[str, str, float, float], ...] = ()

    @property
    def conflict(self) -> bool:
        """True only when two fits of the SAME material disagree."""
        return bool(self.conflicts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "T_c": round(self.temperature_c, 4),
            "spread_log10": None if self.spread_log10 is None else round(self.spread_log10, 3),
            "spread_meaning": "range across different materials, not disagreement",
            "conflict": self.conflict,
            "conflicts": [
                {
                    "a": a,
                    "b": b,
                    "gap_log10": round(gap, 3),
                    "combined_sigma": round(sigma, 3),
                }
                for a, b, gap, sigma in self.conflicts
            ],
            "widest_pair": list(self.widest_pair) if self.widest_pair else None,
            "cells": [c.as_dict() for c in self.cells],
        }


@dataclass(frozen=True)
class ComparisonGroup:
    """Parameterizations that may legitimately be plotted on one axis."""

    quantity: str
    area_basis: str
    units: str
    parameterization_ids: tuple[str, ...]
    material_keys: tuple[str, ...]
    rows: tuple[GridRow, ...]

    @property
    def max_spread_log10(self) -> float | None:
        spreads = [r.spread_log10 for r in self.rows if r.spread_log10 is not None]
        return max(spreads) if spreads else None

    @property
    def n_conflicts(self) -> int:
        return sum(1 for r in self.rows if r.conflict)

    @property
    def same_material_pairs(self) -> int:
        """How many pairs in this group describe the same material at all."""
        keys = self.material_keys
        return sum(
            1 for i, a in enumerate(keys) for b in keys[i + 1 :] if a == b
        )

    @property
    def disagreement_testable(self) -> bool:
        return self.same_material_pairs > 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "quantity": self.quantity,
            "area_basis": self.area_basis,
            "units": self.units,
            "parameterizations": list(self.parameterization_ids),
            "material_keys": list(self.material_keys),
            "max_spread_log10": (
                None if self.max_spread_log10 is None else round(self.max_spread_log10, 3)
            ),
            "n_conflicts": self.n_conflicts,
            "same_material_pairs": self.same_material_pairs,
            "disagreement_testable": self.disagreement_testable,
            "rows": [r.as_dict() for r in self.rows],
        }


def comparison_key(param: Parameterization) -> tuple[str, str]:
    """Fits sharing this key may be compared; fits that do not, may not."""
    return (param.quantity, param.area_basis)


def temperature_grid(lo: float, hi: float, step: float) -> list[float]:
    if step <= 0:
        raise ValueError("step must be positive")
    lo, hi = min(lo, hi), max(lo, hi)
    n = int(round((hi - lo) / step))
    return [round(hi - i * step, 6) for i in range(n + 1)]


def _row(temp: float, params: list[Parameterization]) -> GridRow:
    cells: list[GridCell] = []
    values: list[tuple[str, str, float, float]] = []
    for param in params:
        est = evaluate(param, temp)
        cells.append(
            GridCell(
                parameterization_id=param.id,
                material_key=param.material_key,
                log10_value=est.log10_value,
                sigma_log10=est.sigma_log10,
                in_range=est.in_range,
            )
        )
        if est.log10_value is not None and est.sigma_log10 is not None:
            values.append((param.id, param.material_key, est.log10_value, est.sigma_log10))

    if len(values) < 2:
        return GridRow(temp, tuple(cells), None, None, ())

    lowest = min(values, key=lambda v: v[2])
    highest = max(values, key=lambda v: v[2])

    # A conflict requires the same material. Different substances differing is
    # a result, not a disagreement.
    conflicts: list[tuple[str, str, float, float]] = []
    for i, (id_a, key_a, val_a, sig_a) in enumerate(values):
        for id_b, key_b, val_b, sig_b in values[i + 1 :]:
            if key_a != key_b:
                continue
            gap = abs(val_a - val_b)
            combined = math.sqrt(sig_a**2 + sig_b**2)
            if gap > combined:
                conflicts.append((id_a, id_b, gap, combined))

    return GridRow(
        temperature_c=temp,
        cells=tuple(cells),
        spread_log10=highest[2] - lowest[2],
        widest_pair=(lowest[0], highest[0]),
        conflicts=tuple(conflicts),
    )


def intercompare(
    *,
    temperatures: list[float],
    ids: list[str] | None = None,
    area_basis: str | None = None,
    parameterizations: dict[str, Parameterization] | None = None,
) -> list[ComparisonGroup]:
    """Group the registry into comparable sets and grid them over temperature."""
    registry = parameterizations or load_parameterizations()
    selected = [
        p
        for p in registry.values()
        if (ids is None or p.id in ids)
        and (area_basis is None or p.area_basis == area_basis)
    ]
    if ids:
        missing = set(ids) - {p.id for p in selected}
        if missing:
            raise KeyError(f"unknown parameterization(s): {sorted(missing)}")

    grouped: dict[tuple[str, str], list[Parameterization]] = {}
    for param in selected:
        grouped.setdefault(comparison_key(param), []).append(param)

    groups: list[ComparisonGroup] = []
    for (quantity, basis), params in grouped.items():
        params.sort(key=lambda p: p.id)
        rows = tuple(_row(t, params) for t in temperatures)
        units = "m^-2" if params[0].units == "cm^-2" else params[0].units
        groups.append(
            ComparisonGroup(
                quantity=quantity,
                area_basis=basis,
                units=units,
                parameterization_ids=tuple(p.id for p in params),
                material_keys=tuple(p.material_key for p in params),
                rows=rows,
            )
        )
    groups.sort(key=lambda g: (-len(g.parameterization_ids), g.quantity, g.area_basis))
    return groups


def summarise(groups: list[ComparisonGroup]) -> dict[str, Any]:
    """Top-level read on how much the literature in this build disagrees."""
    comparable = [g for g in groups if len(g.parameterization_ids) > 1]
    worst = max(
        (g for g in comparable if g.max_spread_log10 is not None),
        key=lambda g: g.max_spread_log10 or 0.0,
        default=None,
    )
    testable = [g for g in comparable if g.disagreement_testable]
    return {
        "n_groups": len(groups),
        "n_comparable_groups": len(comparable),
        "n_isolated": len(groups) - len(comparable),
        "n_groups_with_same_material_pairs": len(testable),
        "widest_group": None
        if worst is None
        else {
            "quantity": worst.quantity,
            "area_basis": worst.area_basis,
            "max_spread_log10": round(worst.max_spread_log10 or 0.0, 3),
            "n_conflicts": worst.n_conflicts,
        },
        "note": (
            "Groups are (quantity, surface-area basis); fits in different "
            "groups cannot be compared at all. Within a group, spread is the "
            "range across DIFFERENT materials, which is a result rather than a "
            "disagreement. A conflict is only recorded between two fits of the "
            "same material whose sigma bands fail to overlap - this build has "
            f"{sum(g.same_material_pairs for g in groups)} such pair(s), so "
            "adding a second fit for an existing material is what would make "
            "the disagreement question answerable."
        ),
    }

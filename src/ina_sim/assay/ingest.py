"""Read a droplet-freezing experiment from CSV or JSON.

A laboratory run is (temperature, droplets frozen, droplets total) plus the
surface area carried by each droplet. The counting part is easy; the surface
area is where experiments differ, so three routes are accepted and each one
records how the area was obtained:

    explicit   surface_area_m2_per_droplet given directly (or per row)
    particles  particle_diameter_um x particles_per_droplet, sphere-equivalent
    suspension concentration_g_per_l x droplet_volume_ul x specific surface
               area in m2/g - the usual cold-stage recipe, and the one that
               makes the area BET-derived

`area_basis` (BET or geometric) is mandatory, with no default. It decides which
published fits the result may be compared against, and an experiment that does
not record it cannot be compared to anything without guessing.

CSV metadata may be written as `# key: value` comment lines at the top of the
file, so one file carries both the data and the conditions it was taken under.
CLI flags override file metadata.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ina_sim.units import micrometres_to_metres, sphere_surface_area_m2

AREA_BASES = {"BET", "geometric"}

# Accepted column spellings, lowercased and stripped of spaces/underscores.
_TEMP_KEYS = {"temperaturec", "tc", "tempc", "temperature", "temp"}
_FROZEN_KEYS = {"nfrozen", "frozen", "nice", "nfrozencumulative", "cumulativefrozen"}
_NEW_FROZEN_KEYS = {"nnewlyfrozen", "newlyfrozen", "dn", "nfrozenthisstep"}
_TOTAL_KEYS = {"ntotal", "total", "ndroplets", "droplets", "n"}
_AREA_KEYS = {"surfaceaream2", "aream2", "surfaceaream2perdroplet"}

_NUMERIC_METADATA = {
    "surface_area_m2_per_droplet",
    "particle_diameter_um",
    "particles_per_droplet",
    "concentration_g_per_l",
    "specific_surface_area_m2_per_g",
    "droplet_volume_ul",
    "cooling_rate_k_per_min",
}


class AssayError(ValueError):
    """Raised for anything wrong with an imported experiment file."""


@dataclass(frozen=True)
class AssayMetadata:
    """Everything about the run that is not a per-temperature reading."""

    area_basis: str
    surface_area_m2_per_droplet: float | None = None
    particle_diameter_um: float | None = None
    particles_per_droplet: float | None = None
    concentration_g_per_l: float | None = None
    specific_surface_area_m2_per_g: float | None = None
    droplet_volume_ul: float | None = None
    cooling_rate_k_per_min: float | None = None
    material: str | None = None
    sample: str | None = None
    counting: str = "cumulative"  # cumulative | differential
    notes: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        body = {
            "area_basis": self.area_basis,
            "surface_area_m2_per_droplet": self.surface_area_m2_per_droplet,
            "particle_diameter_um": self.particle_diameter_um,
            "particles_per_droplet": self.particles_per_droplet,
            "concentration_g_per_l": self.concentration_g_per_l,
            "specific_surface_area_m2_per_g": self.specific_surface_area_m2_per_g,
            "droplet_volume_ul": self.droplet_volume_ul,
            "cooling_rate_k_per_min": self.cooling_rate_k_per_min,
            "material": self.material,
            "sample": self.sample,
            "counting": self.counting,
            "notes": self.notes,
        }
        return {k: v for k, v in body.items() if v is not None} | (
            {"extra": self.extra} if self.extra else {}
        )


@dataclass(frozen=True)
class AssayReading:
    """One temperature step: how many of how many droplets had frozen."""

    temperature_c: float
    n_frozen: int
    n_total: int
    surface_area_m2: float | None = None  # per-row override
    source_line: int | None = None


@dataclass(frozen=True)
class RawAssay:
    readings: tuple[AssayReading, ...]
    metadata: AssayMetadata
    path: Path | None
    file_sha256: str | None

    def area_per_droplet_m2(self) -> tuple[float, str]:
        """Resolve droplet surface area and say which route produced it."""
        meta = self.metadata
        if meta.surface_area_m2_per_droplet is not None:
            area = meta.surface_area_m2_per_droplet
            route = "explicit surface_area_m2_per_droplet"
        elif meta.particle_diameter_um is not None:
            count = meta.particles_per_droplet
            if count is None:
                raise AssayError(
                    "particle_diameter_um given without particles_per_droplet; "
                    "the number of particles per droplet is needed to get area"
                )
            area = count * sphere_surface_area_m2(
                micrometres_to_metres(meta.particle_diameter_um)
            )
            route = (
                f"{count:g} sphere-equivalent particles of "
                f"{meta.particle_diameter_um:g} um per droplet"
            )
        elif meta.concentration_g_per_l is not None:
            if meta.specific_surface_area_m2_per_g is None:
                raise AssayError(
                    "concentration_g_per_l given without "
                    "specific_surface_area_m2_per_g; a suspension needs a "
                    "specific surface area (usually BET) to give droplet area"
                )
            if meta.droplet_volume_ul is None:
                raise AssayError(
                    "concentration_g_per_l given without droplet_volume_ul; "
                    "droplet volume is needed to get mass per droplet"
                )
            litres = meta.droplet_volume_ul * 1e-6
            grams = meta.concentration_g_per_l * litres
            area = grams * meta.specific_surface_area_m2_per_g
            route = (
                f"{meta.concentration_g_per_l:g} g/L x {meta.droplet_volume_ul:g} uL "
                f"x {meta.specific_surface_area_m2_per_g:g} m2/g"
            )
        else:
            raise AssayError(
                "cannot determine droplet surface area: give one of "
                "surface_area_m2_per_droplet, "
                "particle_diameter_um + particles_per_droplet, or "
                "concentration_g_per_l + specific_surface_area_m2_per_g + "
                "droplet_volume_ul"
            )
        if not math.isfinite(area) or area <= 0:
            raise AssayError(f"droplet surface area must be positive, got {area!r}")
        return area, route


def _norm_key(key: str) -> str:
    return key.strip().lower().replace(" ", "").replace("_", "").lstrip("﻿")


def _coerce_metadata_value(key: str, value: Any) -> Any:
    if key in _NUMERIC_METADATA and value is not None and not isinstance(value, float):
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise AssayError(f"metadata {key} must be a number, got {value!r}") from exc
    return value


def build_metadata(raw: dict[str, Any], overrides: dict[str, Any] | None = None) -> AssayMetadata:
    merged: dict[str, Any] = {}
    for source in (raw, overrides or {}):
        for key, value in source.items():
            if value is None or value == "":
                continue
            merged[key.strip().lower()] = value

    known = {f for f in AssayMetadata.__dataclass_fields__ if f != "extra"}
    fields: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    for key, value in merged.items():
        if key in known:
            fields[key] = _coerce_metadata_value(key, value)
        else:
            extra[key] = value

    basis = str(fields.get("area_basis", "")).strip()
    if basis not in AREA_BASES:
        raise AssayError(
            "area_basis is required and must be one of "
            f"{sorted(AREA_BASES)} (got {basis!r}). It decides which published "
            "fits this run may be compared against; BET and geometric surface "
            "areas differ by more than an order of magnitude for fine samples."
        )
    fields["area_basis"] = basis

    counting = str(fields.get("counting", "cumulative")).strip().lower()
    if counting not in {"cumulative", "differential"}:
        raise AssayError("counting must be 'cumulative' or 'differential'")
    fields["counting"] = counting

    for key in ("material", "sample", "notes"):
        if key in fields:
            fields[key] = str(fields[key])

    return AssayMetadata(**fields, extra=extra)


def _parse_rows(
    rows: list[dict[str, Any]],
    counting: str,
    *,
    line_offset: int = 0,
) -> list[AssayReading]:
    if not rows:
        raise AssayError("no measurement rows found")

    readings: list[AssayReading] = []
    running = 0
    for index, row in enumerate(rows):
        line = line_offset + index + 1
        norm = {_norm_key(k): v for k, v in row.items() if k is not None}

        temp = _pick(norm, _TEMP_KEYS)
        if temp is None:
            raise AssayError(
                f"row {line}: no temperature column found "
                f"(looked for {sorted(_TEMP_KEYS)})"
            )
        total = _pick(norm, _TOTAL_KEYS)
        if total is None:
            raise AssayError(f"row {line}: no droplet total column found")

        if counting == "differential":
            new_frozen = _pick(norm, _NEW_FROZEN_KEYS)
            if new_frozen is None:
                raise AssayError(
                    f"row {line}: counting=differential needs a newly-frozen column"
                )
            running += int(round(float(new_frozen)))
            frozen_count = running
        else:
            frozen = _pick(norm, _FROZEN_KEYS)
            if frozen is None:
                raise AssayError(
                    f"row {line}: no frozen-count column found "
                    f"(looked for {sorted(_FROZEN_KEYS)})"
                )
            frozen_count = int(round(float(frozen)))

        total_count = int(round(float(total)))
        temp_c = float(temp)
        if not math.isfinite(temp_c):
            raise AssayError(f"row {line}: temperature is not finite")
        if total_count <= 0:
            raise AssayError(f"row {line}: droplet total must be positive")
        if frozen_count < 0 or frozen_count > total_count:
            raise AssayError(
                f"row {line}: frozen count {frozen_count} outside [0, {total_count}]"
            )

        area_raw = _pick(norm, _AREA_KEYS)
        readings.append(
            AssayReading(
                temperature_c=temp_c,
                n_frozen=frozen_count,
                n_total=total_count,
                surface_area_m2=float(area_raw) if area_raw not in (None, "") else None,
                source_line=line,
            )
        )

    readings.sort(key=lambda r: -r.temperature_c)
    _check_monotonic(readings)
    return readings


def _check_monotonic(readings: list[AssayReading]) -> None:
    """Cumulative counts cannot decrease as droplets get colder."""
    previous = None
    for reading in readings:
        fraction = reading.n_frozen / reading.n_total
        if previous is not None and fraction < previous - 1e-9:
            raise AssayError(
                f"row {reading.source_line}: cumulative frozen fraction drops from "
                f"{previous:.4f} to {fraction:.4f} on cooling. Droplets do not "
                "melt on the way down - is this a differential count? Set "
                "counting: differential."
            )
        previous = fraction


def _pick(norm_row: dict[str, Any], keys: set[str]) -> Any:
    for key in keys:
        if key in norm_row and norm_row[key] not in (None, ""):
            return norm_row[key]
    return None


def _read_csv(text: str) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    """Split `# key: value` header comments from the CSV body."""
    meta: dict[str, Any] = {}
    body_lines: list[str] = []
    header_lines = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            header_lines += 1
            content = stripped.lstrip("#").strip()
            if ":" in content:
                key, _, value = content.partition(":")
                meta[key.strip().lower().replace(" ", "_")] = value.strip()
            continue
        if not stripped and not body_lines:
            header_lines += 1
            continue
        body_lines.append(line)
    if not body_lines:
        raise AssayError("file has metadata but no measurement rows")
    reader = csv.DictReader(body_lines)
    return meta, list(reader), header_lines + 1


def load_assay(
    path: str | Path,
    *,
    overrides: dict[str, Any] | None = None,
) -> RawAssay:
    """Load a droplet-freezing run from .csv or .json."""
    path = Path(path)
    if not path.is_file():
        raise AssayError(f"no such file: {path}")
    raw_bytes = path.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()[:16]
    text = raw_bytes.decode("utf-8-sig")

    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AssayError(f"{path}: invalid JSON ({exc})") from exc
        if not isinstance(payload, dict):
            raise AssayError(f"{path}: JSON must be an object with 'measurements'")
        file_meta = dict(payload.get("metadata") or {})
        rows = payload.get("measurements") or payload.get("readings") or []
        if not isinstance(rows, list):
            raise AssayError(f"{path}: 'measurements' must be a list")
        offset = 0
    elif suffix in {".csv", ".tsv", ".txt"}:
        file_meta, rows, offset = _read_csv(text)
    else:
        raise AssayError(
            f"{path}: unsupported extension {suffix!r}; use .csv or .json"
        )

    metadata = build_metadata(file_meta, overrides)
    readings = _parse_rows(rows, metadata.counting, line_offset=offset)
    return RawAssay(
        readings=tuple(readings),
        metadata=metadata,
        path=path,
        file_sha256=digest,
    )

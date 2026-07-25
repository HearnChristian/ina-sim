"""Lightweight request/response validation (no pydantic — offline stdlib)."""

from __future__ import annotations

from typing import Any


SCREEN_RESULT_REQUIRED = {
    "id",
    "name",
    "class",
    "efficiency",
    "relative_ina",
    "relative_ina_low",
    "relative_ina_high",
    "confidence",
    "pathway",
    "source",
}

SCREEN_PAYLOAD_REQUIRED = {
    "version",
    "fidelity",
    "baseline",
    "fingerprint",
    "provenance",
    "conditions",
    "results",
    "literature_xref",
    "assumptions",
    "empirical_claims",
    "score_scale",
}

def validate_screen_row(row: dict[str, Any]) -> list[str]:
    errs = []
    missing = SCREEN_RESULT_REQUIRED - set(row)
    if missing:
        errs.append(f"row missing keys: {sorted(missing)}")
    for k in ("efficiency", "relative_ina", "relative_ina_low", "relative_ina_high"):
        if k in row and row[k] is not None:
            try:
                v = float(row[k])
                if not (v == v):  # NaN
                    errs.append(f"{k} is NaN")
            except (TypeError, ValueError):
                errs.append(f"{k} not numeric")
    return errs


def validate_screen_payload(payload: dict[str, Any]) -> list[str]:
    errs = []
    missing = SCREEN_PAYLOAD_REQUIRED - set(payload)
    if missing:
        errs.append(f"payload missing keys: {sorted(missing)}")
    results = payload.get("results")
    if not isinstance(results, list):
        errs.append("results must be a list")
        return errs
    for i, row in enumerate(results[:20]):
        if not isinstance(row, dict):
            errs.append(f"results[{i}] not object")
            continue
        errs.extend(f"results[{i}]: {e}" for e in validate_screen_row(row))
    lit = payload.get("literature_xref") or {}
    if "summary" not in lit:
        errs.append("literature_xref.summary missing")
    return errs


def assert_screen_payload(payload: dict[str, Any]) -> None:
    errs = validate_screen_payload(payload)
    if errs:
        raise ValueError("; ".join(errs))

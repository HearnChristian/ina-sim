"""What is actually known about a candidate, as opposed to what is scored.

The heuristic ranking answers "which of these would I try first". This module
answers the harder question: "what has anybody measured?" For most of the
library the answer is nothing, and saying so plainly is the point. Three
outcomes are possible for any candidate:

    measured  a published (or explicitly derived) parameterization covers it,
              so ns(T) or J(T) comes with units, a validity range, an
              uncertainty and a citation;
    solute    it is a soluble salt, which depresses the freezing point and
              suppresses ice nucleation - there is no ns to report and
              pretending otherwise is the error this module exists to prevent;
    none      nobody has measured it in a form this tool can use.

`evidence_for` never invents a number to fill a gap.
"""

from __future__ import annotations

from typing import Any

from ina_sim.models.candidate import Candidate
from ina_sim.physics.freezing import (
    frozen_fraction_singular,
    median_freezing_temperature,
)
from ina_sim.physics.ns import (
    Estimate,
    evaluate_for_candidate,
    parameterizations_for,
)
from ina_sim.physics.solutes import is_solute, solute_statement
from ina_sim.units import micrometres_to_metres, sphere_surface_area_m2

EVIDENCE_MEASURED = "measured"
EVIDENCE_SOLUTE = "solute"
EVIDENCE_NONE = "none"


def _observables(est: Estimate, particle_diameter_um: float) -> dict[str, Any]:
    """Turn an ns value into quantities a droplet-freezing assay would report."""
    area_m2 = sphere_surface_area_m2(micrometres_to_metres(particle_diameter_um))
    out: dict[str, Any] = {
        "particle_diameter_um": particle_diameter_um,
        "particle_surface_area_m2": area_m2,
        "area_note": (
            "sphere-equivalent geometric area of one particle; the "
            "parameterization's own area basis is reported alongside ns"
        ),
    }
    if est.quantity != "ns" or est.value is None:
        return out
    out["frozen_fraction_one_particle"] = round(
        frozen_fraction_singular(est.value, area_m2), 5
    )
    if est.low is not None and est.high is not None:
        out["frozen_fraction_low"] = round(frozen_fraction_singular(est.low, area_m2), 5)
        out["frozen_fraction_high"] = round(
            frozen_fraction_singular(est.high, area_m2), 5
        )
    return out


def evidence_for(
    candidate: Candidate,
    temperature_c: float,
    *,
    particle_diameter_um: float = 1.0,
    mode: str = "immersion",
) -> dict[str, Any]:
    """Empirical evidence block for one candidate at one temperature."""
    if is_solute(candidate.id):
        return {
            "evidence": EVIDENCE_SOLUTE,
            "ns": None,
            "statement": solute_statement(candidate.id),
            "reference": "koop2000",
            "parameterizations_available": 0,
        }

    params = parameterizations_for(candidate.id)
    if not params:
        return {
            "evidence": EVIDENCE_NONE,
            "ns": None,
            "statement": (
                f"no ice nucleation parameterization in this build covers "
                f"{candidate.id}; its ranking is heuristic only and carries no "
                "measured active site density"
            ),
            "parameterizations_available": 0,
        }

    est = evaluate_for_candidate(
        candidate.id, temperature_c, mode=mode, allow_extrapolation=False
    )
    if est is None:
        return {
            "evidence": EVIDENCE_NONE,
            "ns": None,
            "statement": "parameterization lookup returned nothing",
            "parameterizations_available": len(params),
        }

    block: dict[str, Any] = {
        "evidence": EVIDENCE_MEASURED,
        "ns": est.as_dict(),
        "parameterizations_available": len(params),
        "observables": _observables(est, particle_diameter_um),
    }

    if est.value is None:
        block["statement"] = (
            f"{est.material}: measured, but {temperature_c:g} C lies outside the "
            f"range the source fitted, so no value is reported"
        )
        return block

    label = "published fit" if est.status == "published" else "in-repo derived fit"
    block["statement"] = (
        f"{est.material}: {est.quantity} = {est.value:.3g} {est.units} at "
        f"{temperature_c:g} C ({label}, {est.citation}), 1 sigma "
        f"{est.sigma_log10:.2g} decades"
        + (" (assumed, not stated by the source)" if est.sigma_assumed else "")
    )

    if est.quantity == "ns":
        area_m2 = sphere_surface_area_m2(micrometres_to_metres(particle_diameter_um))
        param = next((p for p in params if p.id == est.parameterization_id), None)
        if param is not None:
            t50 = median_freezing_temperature(param, area_m2)
            block["observables"]["t50_c"] = t50
            block["observables"]["t50_note"] = (
                "temperature at which half of droplets each carrying one such "
                "particle would be frozen; null means the crossing lies outside "
                "the fitted range"
            )
    return block


def evidence_summary(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate how much of a screen is backed by measurements."""
    counts = {EVIDENCE_MEASURED: 0, EVIDENCE_SOLUTE: 0, EVIDENCE_NONE: 0}
    with_value = 0
    for block in blocks:
        kind = block.get("evidence", EVIDENCE_NONE)
        counts[kind] = counts.get(kind, 0) + 1
        ns = block.get("ns")
        if ns and ns.get("value") is not None:
            with_value += 1
    total = len(blocks) or 1
    return {
        "n_candidates": len(blocks),
        "measured": counts[EVIDENCE_MEASURED],
        "solute": counts[EVIDENCE_SOLUTE],
        "unmeasured": counts[EVIDENCE_NONE],
        "with_value_at_this_temperature": with_value,
        "fraction_measured": round(counts[EVIDENCE_MEASURED] / total, 3),
        "note": (
            "measured means a parameterization exists for the material, not "
            "that a value is available at this temperature; a parameterization "
            "outside its fitted range deliberately returns nothing"
        ),
    }

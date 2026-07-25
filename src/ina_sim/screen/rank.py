"""L0/L1 screening and ranking (+ CNT educational details + uncertainty)."""

from __future__ import annotations

import math

from ina_sim.bridge.ina_per_kg import ina_per_kg_proxy, relative_ina_score
from ina_sim.models.candidate import Candidate, Confidence
from ina_sim.models.conditions import Conditions
from ina_sim.models.results import ScreenResult
from ina_sim.physics.activity import uncertainty_fraction
from ina_sim.physics.atmosphere import atmosphere_state, total_water_vapor_kg
from ina_sim.physics.cnt import cnt_estimate
from ina_sim.physics.dose import activation
from ina_sim.physics.efficiency import agent_efficiency, condensable_water_kg
from ina_sim.physics.evidence import EVIDENCE_MEASURED, EVIDENCE_SOLUTE, evidence_for


def screen_one(candidate: Candidate, conditions: Conditions) -> ScreenResult:
    conditions.validate()
    eff = agent_efficiency(candidate, conditions)
    vapor = total_water_vapor_kg(
        conditions.cloud_volume_m3,
        conditions.temperature_c,
        conditions.relative_humidity_pct,
        conditions.pressure_hpa,
    )
    condensable = condensable_water_kg(vapor, eff)
    rel = relative_ina_score(eff.overall)
    if not math.isfinite(rel):
        rel = 0.0

    conf = candidate.default_confidence()
    exploratory_tag = "upload" in candidate.tags or "exploratory" in candidate.tags
    if candidate.agent_class.value == "organic" or exploratory_tag:
        conf = Confidence.EXPLORATORY
    if candidate.source == "upload":
        conf = Confidence.EXPLORATORY
    u = uncertainty_fraction(conf.value)
    rel_lo = max(0.0, rel * (1.0 - u))
    rel_hi = rel * (1.0 + u)

    ina_kg = ina_per_kg_proxy(
        candidate,
        eff.overall,
        diameter_um=conditions.particle_diameter_um,
    )
    if ina_kg is not None and not math.isfinite(ina_kg):
        ina_kg = None

    atm = atmosphere_state(
        conditions.temperature_c,
        conditions.relative_humidity_pct,
        conditions.pressure_hpa,
        conditions.cloud_volume_m3,
    )
    cnt = cnt_estimate(
        conditions.temperature_c,
        atm.s_ice if conditions.mode == "deposition" else max(atm.s_ice, 1.0),
        lattice_match=candidate.lattice_match_score
        if candidate.agent_class.value == "ice_nucleant"
        else None,
    )

    evidence = evidence_for(
        candidate,
        conditions.temperature_c,
        particle_diameter_um=conditions.particle_diameter_um,
        mode=conditions.mode,
    )

    # Particle size and dose. Uses the measured ns where one exists, otherwise
    # reads the heuristic score as an activation probability at the reference
    # diameter (see physics/dose.py). At the default 1 µm this reproduces the
    # score exactly; away from it the d^2 surface-area scaling applies.
    ns_block = evidence.get("ns") or {}
    act = activation(
        temperature_c=conditions.temperature_c,
        score=eff.overall,
        particle_diameter_um=conditions.particle_diameter_um,
        seeding_density_per_l=conditions.seeding_density_per_l,
        measured_ns_m2=ns_block.get("value"),
        is_measured_material=evidence["evidence"] == EVIDENCE_MEASURED,
        measured_quantity=str(ns_block.get("quantity", "ns")),
        citation=ns_block.get("citation"),
    )

    warnings: list[str] = []
    if evidence["evidence"] == EVIDENCE_SOLUTE:
        warnings.append(
            f"{candidate.id} is a soluble salt: it depresses the freezing point "
            "and has no measured ice nucleation active site density"
        )
    elif evidence["evidence"] != EVIDENCE_MEASURED:
        warnings.append(
            f"{candidate.id} has no ice nucleation parameterization in this "
            "build; its score is heuristic, not measured"
        )
    elif (evidence.get("ns") or {}).get("value") is None:
        warnings.append(
            f"{candidate.id}: measured, but {conditions.temperature_c:g} °C is "
            "outside the fitted range of its parameterization"
        )
    if candidate.agent_class.value == "organic":
        warnings.append("organic class is exploratory; not for payload claims")
    if candidate.agent_class.value == "hygroscopic":
        warnings.append(
            "hygroscopic mechanism ≠ ice nucleation; compare carefully to AgI"
        )
        if conditions.track == "ice":
            warnings.append(
                "ice track: hygroscopic agents demoted "
                "(use warm_cloud track for CCN ranking)"
            )
    if conditions.mode == "deposition" and not atm.ice_supersaturated:
        warnings.append("deposition mode: parcel not ice-supersaturated (S_i ≤ 1)")
    if conditions.mode == "immersion" and conditions.temperature_c >= 0:
        warnings.append("immersion mode above 0 °C: ice nucleants heavily penalized")
    if conditions.track == "warm_cloud" and candidate.agent_class.value == "ice_nucleant":
        warnings.append("warm_cloud track: ice nucleants demoted (not the ranking target)")
    if ina_kg is None:
        warnings.append("missing density; ina_per_kg_proxy unavailable")
    if candidate.source == "upload":
        warnings.append("upload placeholder efficiency — builder feed only")

    return ScreenResult(
        candidate=candidate,
        conditions=conditions,
        overall_efficiency=eff.overall,
        efficiency_rating=eff.rating,
        temp_efficiency_factor=eff.temp_factor,
        density_efficiency_factor=eff.density_factor,
        total_water_vapor_kg=vapor,
        condensable_water_kg=condensable,
        relative_ina_score=rel,
        relative_ina_low=rel_lo,
        relative_ina_high=rel_hi,
        ina_per_kg_proxy=ina_kg,
        confidence=conf,
        fidelity="L0+L1-table+CNT",
        warnings=warnings,
        details={
            "supersaturation_factor": eff.supersaturation_factor,
            "mode_factor": round(eff.mode_factor, 4),
            "class_factor": round(eff.class_factor, 4),
            "cnt_score": round(eff.cnt_score, 4),
            "pathway": eff.pathway,
            "temp_method": eff.temp_method,
            "citation": eff.citation,
            "source": candidate.source,
            "uncertainty_frac": u,
            "optimal_temp_c": candidate.optimal_temp_c,
            "base_efficiency": candidate.base_efficiency,
            "s_water": round(atm.s_water, 4),
            "s_ice": round(atm.s_ice, 4),
            "rh_ice_pct": round(atm.rh_ice_pct, 2),
            "track": conditions.track,
            "cnt": cnt.as_dict(),
            "evidence": evidence,
            "activation": act.as_dict(),
        },
    )


def rank_candidates(
    candidates: list[Candidate],
    conditions: Conditions,
    *,
    sort_key: str = "relative_ina",
) -> list[ScreenResult]:
    results = [screen_one(c, conditions) for c in candidates]

    def key_fn(r: ScreenResult) -> float:
        if sort_key == "efficiency":
            return r.overall_efficiency
        if sort_key == "condensable":
            return r.condensable_water_kg
        if sort_key == "ina_per_kg":
            return r.ina_per_kg_proxy or 0.0
        if sort_key == "cnt_score":
            return float(r.details.get("cnt_score") or 0.0)
        return r.relative_ina_score

    return sorted(results, key=key_fn, reverse=True)


def temperature_sweep(
    candidates: list[Candidate],
    *,
    t_min: float = -30.0,
    t_max: float = 0.0,
    step: float = 2.0,
    relative_humidity_pct: float = 95.0,
    pressure_hpa: float = 850.0,
    mode: str = "immersion",
    track: str = "ice",
    seeding_density_per_l: float = 100.0,
    particle_diameter_um: float = 1.0,
    cloud_volume_m3: float = 1e6,
    max_points: int = 200,
) -> list[dict]:
    if step <= 0 or not math.isfinite(step):
        raise ValueError("step must be a positive finite number")
    if not math.isfinite(t_min) or not math.isfinite(t_max):
        raise ValueError("t_min/t_max must be finite")
    if t_max < t_min:
        t_min, t_max = t_max, t_min
    n_est = int((t_max - t_min) / step) + 1
    if n_est > max_points:
        step = max(step, (t_max - t_min) / max(1, max_points - 1))

    out: list[dict] = []
    t = t_min
    for _ in range(max_points + 5):
        if t > t_max + 1e-9:
            break
        conditions = Conditions(
            temperature_c=round(t, 4),
            relative_humidity_pct=relative_humidity_pct,
            pressure_hpa=pressure_hpa,
            mode=mode,
            track=track,
            seeding_density_per_l=seeding_density_per_l,
            particle_diameter_um=particle_diameter_um,
            cloud_volume_m3=cloud_volume_m3,
        ).clamped()
        ranked = rank_candidates(candidates, conditions)
        out.append(
            {
                "T_c": conditions.temperature_c,
                "rankings": [
                    {
                        "id": r.candidate.id,
                        "relative_ina": round(r.relative_ina_score, 4),
                        "relative_ina_low": round(r.relative_ina_low, 4),
                        "relative_ina_high": round(r.relative_ina_high, 4),
                        "efficiency": round(r.overall_efficiency, 4),
                        "cnt_score": r.details.get("cnt_score"),
                        "pathway": r.details.get("pathway"),
                        # Size- and dose-dependent quantities, so a sweep of
                        # these actually responds to the diameter and density
                        # inputs rather than being a fixed curve.
                        "activation_probability": (
                            (r.details.get("activation") or {}).get(
                                "activation_probability"
                            )
                        ),
                        "n_inp_per_litre": (
                            (r.details.get("activation") or {}).get("n_inp_per_litre")
                        ),
                    }
                    for r in ranked
                ],
            }
        )
        t += step
    return out

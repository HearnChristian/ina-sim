"""L0/L1 heuristic screening and ranking."""

from __future__ import annotations

from ina_sim.bridge.ina_per_kg import ina_per_kg_proxy, relative_ina_score
from ina_sim.models.candidate import Candidate, Confidence
from ina_sim.models.conditions import Conditions
from ina_sim.models.results import ScreenResult
from ina_sim.physics.atmosphere import total_water_vapor_kg
from ina_sim.physics.efficiency import agent_efficiency, condensable_water_kg


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
    ina_kg = ina_per_kg_proxy(candidate, eff.overall)

    warnings: list[str] = []
    conf = candidate.default_confidence()
    if candidate.agent_class.value == "organic":
        warnings.append("organic class is exploratory; not for payload claims")
        conf = Confidence.EXPLORATORY
    if candidate.agent_class.value == "hygroscopic":
        warnings.append(
            "hygroscopic mechanism ≠ ice nucleation; compare carefully to AgI"
        )
    if conditions.mode != "immersion":
        warnings.append(f"mode={conditions.mode} not fully modeled yet; immersion proxy used")
    if ina_kg is None:
        warnings.append("missing density; ina_per_kg_proxy unavailable")

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
        ina_per_kg_proxy=ina_kg,
        confidence=conf,
        fidelity="L0+L1-heuristic",
        warnings=warnings,
        details={
            "supersaturation_factor": eff.supersaturation_factor,
            "optimal_temp_c": candidate.optimal_temp_c,
            "base_efficiency": candidate.base_efficiency,
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
        return r.relative_ina_score

    return sorted(results, key=key_fn, reverse=True)

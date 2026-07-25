"""Export provenance: version, assumptions, hashes."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ina_sim import __version__
from ina_sim.models.conditions import Conditions


DEFAULT_ASSUMPTIONS = {
    "particle_model": "monodisperse spheres",
    "active_site_fraction": 0.01,
    "relative_score_scale": "0–1 with AgI peak_strength=1; score=peak×a(T)×mode×load",
    "fidelity": "L0+L1-table+CNT",
    "cnt_role": "diagnostic only (≤2% blend); default rank key is relative score",
    "activity_tables": "library/activity_curves.yaml — a(T) shapes from public literature direction",
    "disclaimer": (
        "Relative screening model for empirical ranking claims under stated assumptions. "
        "Does not output absolute INP concentrations or precipitation forecasts. "
        "See empirical_claims in each screen payload for what this run supports."
    ),
}


def fingerprint_conditions(
    conditions: Conditions,
    *,
    sort_key: str,
    starter_set: bool,
) -> str:
    return (
        f"T={conditions.temperature_c:.4g}|RH={conditions.relative_humidity_pct:.4g}|"
        f"P={conditions.pressure_hpa:.4g}|den={conditions.seeding_density_per_l:.4g}|"
        f"d={conditions.particle_diameter_um:.4g}|mode={conditions.mode}|"
        f"track={conditions.track}|sort={sort_key}|starter={int(starter_set)}"
    )


def param_hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_provenance(
    conditions: Conditions,
    *,
    sort_key: str,
    starter_set: bool,
    n_agents: int,
    extra: dict | None = None,
) -> dict[str, Any]:
    assumptions = {
        **DEFAULT_ASSUMPTIONS,
        "particle_diameter_um": conditions.particle_diameter_um,
        "seeding_density_per_l": conditions.seeding_density_per_l,
        "cloud_volume_m3": conditions.cloud_volume_m3,
        "track": conditions.track,
        "mode": conditions.mode,
    }
    body = {
        "version": __version__,
        "conditions": conditions.as_dict(),
        "sort_key": sort_key,
        "starter_set": starter_set,
        "n_agents": n_agents,
        "assumptions": assumptions,
    }
    if extra:
        body["extra"] = extra
    return {
        "version": __version__,
        "param_hash": param_hash(body),
        "fingerprint": fingerprint_conditions(
            conditions, sort_key=sort_key, starter_set=starter_set
        ),
        "assumptions": assumptions,
        "n_agents": n_agents,
        "sort_key": sort_key,
    }

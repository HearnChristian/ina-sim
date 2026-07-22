from __future__ import annotations

from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Iterable

import yaml

from ina_sim.models.candidate import AgentClass, Candidate


def _parse_candidate(raw: dict) -> Candidate:
    return Candidate(
        id=str(raw["id"]),
        name=str(raw["name"]),
        formula=raw.get("formula"),
        agent_class=AgentClass(raw.get("agent_class", "unknown")),
        base_efficiency=float(raw.get("base_efficiency", 0.5)),
        optimal_temp_c=float(raw.get("optimal_temp_c", -10.0)),
        lattice_match_score=(
            None
            if raw.get("lattice_match_score") is None
            else float(raw["lattice_match_score"])
        ),
        density_g_cm3=(
            None if raw.get("density_g_cm3") is None else float(raw["density_g_cm3"])
        ),
        notes=str(raw.get("notes", "")),
        source=str(raw.get("source", "library")),
        tags=tuple(raw.get("tags") or ()),
        meta={k: v for k, v in raw.items() if k not in {
            "id", "name", "formula", "agent_class", "base_efficiency",
            "optimal_temp_c", "lattice_match_score", "density_g_cm3",
            "notes", "source", "tags",
        }},
    )


def load_candidates_from_path(path: Path | str) -> list[Candidate]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return [_parse_candidate(c) for c in data.get("candidates", [])]


@lru_cache(maxsize=1)
def load_candidates() -> tuple[Candidate, ...]:
    """Load packaged default library."""
    ref = resources.files("ina_sim.library").joinpath("candidates.yaml")
    with ref.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return tuple(_parse_candidate(c) for c in data.get("candidates", []))


def get_candidate(candidate_id: str) -> Candidate:
    for c in load_candidates():
        if c.id == candidate_id:
            return c
    raise KeyError(f"Unknown candidate id: {candidate_id}")


def filter_candidates(
    ids: Iterable[str] | None = None,
    tags: Iterable[str] | None = None,
) -> list[Candidate]:
    pool = list(load_candidates())
    if ids:
        id_set = set(ids)
        pool = [c for c in pool if c.id in id_set]
    if tags:
        tag_set = set(tags)
        pool = [c for c in pool if tag_set.intersection(c.tags)]
    return pool

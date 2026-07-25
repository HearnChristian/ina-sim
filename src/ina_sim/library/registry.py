"""Mutable session + disk-backed candidate registry (uploads / builder feed).

Packaged ``candidates.yaml`` stays immutable. User-uploaded molecules live here
and are merged into screening when requested.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from ina_sim.models.candidate import Candidate

_lock = threading.RLock()
_session: dict[str, Candidate] = {}


def default_upload_dir() -> Path:
    """Prefer project data/uploads; fall back to cwd/data/uploads."""
    # Walk up from this file: src/ina_sim/library → repo root
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src").is_dir():
            return parent / "data" / "uploads"
    return Path.cwd() / "data" / "uploads"


def list_session() -> list[Candidate]:
    with _lock:
        return list(_session.values())


def get_session(candidate_id: str) -> Candidate | None:
    with _lock:
        return _session.get(candidate_id)


def register(candidate: Candidate, *, persist: bool = True) -> Candidate:
    """Add/replace a session candidate; optionally write JSON under data/uploads/."""
    with _lock:
        _session[candidate.id] = candidate
        if persist:
            _persist(candidate)
        return candidate


def unregister(candidate_id: str, *, delete_file: bool = True) -> bool:
    with _lock:
        existed = candidate_id in _session
        _session.pop(candidate_id, None)
        if delete_file:
            path = default_upload_dir() / f"{candidate_id}.json"
            if path.is_file():
                path.unlink()
        return existed


def clear_session(*, delete_files: bool = False) -> int:
    with _lock:
        n = len(_session)
        ids = list(_session.keys())
        _session.clear()
        if delete_files:
            for cid in ids:
                path = default_upload_dir() / f"{cid}.json"
                if path.is_file():
                    path.unlink()
        return n


def load_persisted(directory: Path | None = None) -> int:
    """Load previously uploaded JSON candidates from disk into session."""
    d = directory or default_upload_dir()
    if not d.is_dir():
        return 0
    count = 0
    for path in sorted(d.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            cand = _candidate_from_dict(raw)
            with _lock:
                _session[cand.id] = cand
            count += 1
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
    return count


def _persist(candidate: Candidate) -> Path:
    d = default_upload_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{candidate.id}.json"
    path.write_text(
        json.dumps(candidate_to_dict(candidate), indent=2),
        encoding="utf-8",
    )
    return path


def candidate_to_dict(c: Candidate) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "formula": c.formula,
        "agent_class": c.agent_class.value,
        "base_efficiency": c.base_efficiency,
        "optimal_temp_c": c.optimal_temp_c,
        "lattice_match_score": c.lattice_match_score,
        "density_g_cm3": c.density_g_cm3,
        "notes": c.notes,
        "source": c.source,
        "tags": list(c.tags),
        "meta": c.meta,
    }


def _candidate_from_dict(raw: dict) -> Candidate:
    from ina_sim.models.candidate import AgentClass

    return Candidate(
        id=str(raw["id"]),
        name=str(raw.get("name") or raw["id"]),
        formula=raw.get("formula"),
        agent_class=AgentClass(raw.get("agent_class", "organic")),
        base_efficiency=float(raw.get("base_efficiency", 0.35)),
        optimal_temp_c=float(raw.get("optimal_temp_c", -15.0)),
        lattice_match_score=(
            None
            if raw.get("lattice_match_score") is None
            else float(raw["lattice_match_score"])
        ),
        density_g_cm3=(
            None if raw.get("density_g_cm3") is None else float(raw["density_g_cm3"])
        ),
        notes=str(raw.get("notes", "")),
        source=str(raw.get("source", "upload")),
        tags=tuple(raw.get("tags") or ("upload", "exploratory")),
        meta=dict(raw.get("meta") or {}),
    )

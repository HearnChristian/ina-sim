"""Parse molecular uploads into screening Candidates (builder feed, offline).

Supported formats (stdlib only — no RDKit required for offline use):

- **json** — full candidate descriptor or ``{smiles, name, ...}``
- **smiles** — SMILES string (heuristic atom inventory + descriptors)
- **xyz** — XYZ coordinate file
- **mol** / **sdf** — basic V2000 molfile atom/bond parse

All uploads are tagged exploratory / low confidence until a molecular builder
and wet-lab path exist. Heuristic ``base_efficiency`` is a placeholder so the
agent can enter the rank table — not a prediction of nucleation skill.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from ina_sim.models.candidate import AgentClass, Candidate

# Common element symbols longest-first for SMILES tokenization
_ELEMENTS = (
    "He", "Li", "Be", "Ne", "Na", "Mg", "Al", "Si", "Cl", "Ar", "Ca", "Ti",
    "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Ga", "Ge", "As", "Se", "Br",
    "Kr", "Rb", "Sr", "Zr", "Mo", "Ag", "Cd", "In", "Sn", "Sb", "Te", "Xe",
    "Ba", "Pt", "Au", "Hg", "Pb", "Bi", "I", "B", "C", "N", "O", "F", "P",
    "S", "K", "V", "Y", "W", "H",
)
_EL_RE = re.compile(
    r"(" + "|".join(sorted(_ELEMENTS, key=len, reverse=True)) + r")"
)
_ID_SAFE = re.compile(r"[^a-z0-9_]+")


@dataclass
class MoleculeRecord:
    """Normalized molecular payload ready for the builder / registry."""

    format: str
    atoms: list[str] = field(default_factory=list)
    coords: list[tuple[float, float, float]] | None = None
    bonds: list[tuple[int, int, int]] | None = None  # i, j, order (0-based)
    smiles: str | None = None
    formula: str | None = None
    n_atoms: int = 0
    element_counts: dict[str, int] = field(default_factory=dict)
    descriptors: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    raw_preview: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "n_atoms": self.n_atoms,
            "atoms": self.atoms,
            "coords": self.coords,
            "bonds": self.bonds,
            "smiles": self.smiles,
            "formula": self.formula,
            "element_counts": self.element_counts,
            "descriptors": self.descriptors,
            "warnings": self.warnings,
            "raw_preview": self.raw_preview[:500],
        }


def slug_id(name: str, content: str) -> str:
    base = _ID_SAFE.sub("_", name.strip().lower()).strip("_") or "mol"
    if not base[0].isalpha():
        base = "m_" + base
    h = hashlib.sha1(content.encode("utf-8")).hexdigest()[:8]
    return f"{base[:40]}_{h}"


def formula_from_counts(counts: dict[str, int]) -> str:
    """Hill-order-ish formula string."""
    if not counts:
        return "Unknown"
    order = []
    if "C" in counts:
        order.append("C")
        if "H" in counts:
            order.append("H")
    for el in sorted(counts):
        if el in order:
            continue
        order.append(el)
    parts = []
    for el in order:
        n = counts[el]
        parts.append(el if n == 1 else f"{el}{n}")
    return "".join(parts)


def _count_elements(atoms: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in atoms:
        out[a] = out.get(a, 0) + 1
    return out


def parse_smiles(smiles: str) -> MoleculeRecord:
    s = smiles.strip()
    if not s:
        raise ValueError("empty SMILES")
    if len(s) > 5000:
        raise ValueError("SMILES too long (max 5000 chars)")
    # Strip common aromatic/organic shorthand noise for counting
    # Bracket atoms: [NH4+], [Fe+2], [C@H]
    atoms: list[str] = []
    warnings: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "[":
            j = s.find("]", i)
            if j < 0:
                raise ValueError("unclosed [ in SMILES")
            inside = s[i + 1 : j]
            m = re.match(r"(\d+)?([A-Z][a-z]?)", inside)
            if not m:
                raise ValueError(f"bad bracket atom in SMILES: [{inside}]")
            atoms.append(m.group(2))
            i = j + 1
            continue
        if ch in "()=#+\\/@.-:%0123456789":
            i += 1
            continue
        if ch.islower() and ch in "bcnosp":
            atoms.append({"b": "B", "c": "C", "n": "N", "o": "O", "p": "P", "s": "S"}[ch])
            i += 1
            continue
        m = _EL_RE.match(s, i)
        if m:
            atoms.append(m.group(1))
            i = m.end()
            continue
        # ignore other punctuation
        if ch.isalpha():
            warnings.append(f"unrecognized token near {s[i:i+4]!r}")
        i += 1

    if not atoms:
        raise ValueError("no atoms parsed from SMILES")
    counts = _count_elements(atoms)
    rec = MoleculeRecord(
        format="smiles",
        atoms=atoms,
        smiles=s,
        formula=formula_from_counts(counts),
        n_atoms=len(atoms),
        element_counts=counts,
        warnings=warnings,
        raw_preview=s,
        descriptors=_heuristic_descriptors(counts, atoms),
    )
    return rec


def parse_xyz(text: str) -> MoleculeRecord:
    lines = [ln.rstrip() for ln in text.strip().splitlines() if ln.strip() != "" or True]
    # standard XYZ: n, comment, then n lines
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(raw_lines) < 3:
        raise ValueError("XYZ too short")
    try:
        n = int(raw_lines[0].strip())
    except ValueError as e:
        raise ValueError("XYZ first line must be atom count") from e
    if n < 1 or n > 50_000:
        raise ValueError("XYZ atom count out of range")
    atoms: list[str] = []
    coords: list[tuple[float, float, float]] = []
    body = raw_lines[2:]
    for i in range(n):
        if i >= len(body):
            raise ValueError(f"XYZ expected {n} atom lines, found {i}")
        parts = body[i].split()
        if len(parts) < 4:
            raise ValueError(f"XYZ atom line {i+1} needs: Element x y z")
        el = parts[0]
        # strip isotope style
        el = re.sub(r"\d+", "", el)
        el = el[0].upper() + el[1:].lower() if len(el) > 1 else el.upper()
        try:
            x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
        except ValueError as e:
            raise ValueError(f"XYZ bad coordinates on line {i+1}") from e
        atoms.append(el)
        coords.append((x, y, z))
    counts = _count_elements(atoms)
    return MoleculeRecord(
        format="xyz",
        atoms=atoms,
        coords=coords,
        formula=formula_from_counts(counts),
        n_atoms=len(atoms),
        element_counts=counts,
        raw_preview="\n".join(raw_lines[: min(12, len(raw_lines))]),
        descriptors=_heuristic_descriptors(counts, atoms, coords=coords),
    )


def parse_mol(text: str) -> MoleculeRecord:
    """Minimal V2000 molfile / single-record SDF parse."""
    raw = text.replace("\r\n", "\n").replace("\r", "\n")
    # SDF: take first record
    if "$$$$" in raw:
        raw = raw.split("$$$$")[0]
    lines = raw.split("\n")
    # Find counts line: aaaabbb... (atoms bonds) — often line index 3
    counts_idx = None
    for i, ln in enumerate(lines[:10]):
        if re.match(r"^\s*\d+\s+\d+", ln):
            counts_idx = i
            break
    if counts_idx is None:
        raise ValueError("molfile: could not find counts line")
    parts = lines[counts_idx].split()
    n_atoms = int(parts[0])
    n_bonds = int(parts[1]) if len(parts) > 1 else 0
    if n_atoms < 1 or n_atoms > 50_000:
        raise ValueError("molfile atom count out of range")
    atoms: list[str] = []
    coords: list[tuple[float, float, float]] = []
    base = counts_idx + 1
    for i in range(n_atoms):
        ln = lines[base + i] if base + i < len(lines) else ""
        p = ln.split()
        if len(p) < 4:
            raise ValueError(f"molfile atom block incomplete at atom {i+1}")
        x, y, z = float(p[0]), float(p[1]), float(p[2])
        el = p[3]
        el = el[0].upper() + el[1:].lower() if len(el) > 1 else el.upper()
        atoms.append(el)
        coords.append((x, y, z))
    bonds: list[tuple[int, int, int]] = []
    b0 = base + n_atoms
    for i in range(n_bonds):
        if b0 + i >= len(lines):
            break
        p = lines[b0 + i].split()
        if len(p) < 3:
            continue
        a1, a2, order = int(p[0]) - 1, int(p[1]) - 1, int(float(p[2]))
        bonds.append((a1, a2, order))
    counts = _count_elements(atoms)
    return MoleculeRecord(
        format="mol",
        atoms=atoms,
        coords=coords,
        bonds=bonds,
        formula=formula_from_counts(counts),
        n_atoms=len(atoms),
        element_counts=counts,
        raw_preview="\n".join(lines[: min(15, len(lines))]),
        descriptors=_heuristic_descriptors(counts, atoms, coords=coords),
    )


def _heuristic_descriptors(
    counts: dict[str, int],
    atoms: list[str],
    coords: list[tuple[float, float, float]] | None = None,
) -> dict[str, Any]:
    n = max(1, len(atoms))
    heavy = sum(1 for a in atoms if a != "H")
    polar = sum(counts.get(e, 0) for e in ("O", "N", "F", "Cl", "S", "P"))
    metals = sum(
        counts.get(e, 0)
        for e in ("Ag", "Fe", "Cu", "Zn", "Al", "Ti", "Ni", "Co", "Mn", "Au", "Pt")
    )
    desc: dict[str, Any] = {
        "n_heavy": heavy,
        "n_polar": polar,
        "n_metals": metals,
        "frac_polar": round(polar / n, 4),
        "has_halogen": any(counts.get(e, 0) for e in ("F", "Cl", "Br", "I")),
        "has_silver": counts.get("Ag", 0) > 0,
        "has_iodine": counts.get("I", 0) > 0,
    }
    if coords and len(coords) == len(atoms) and len(coords) >= 2:
        import math

        cx = sum(c[0] for c in coords) / len(coords)
        cy = sum(c[1] for c in coords) / len(coords)
        cz = sum(c[2] for c in coords) / len(coords)
        rg2 = sum((c[0] - cx) ** 2 + (c[1] - cy) ** 2 + (c[2] - cz) ** 2 for c in coords) / len(coords)
        desc["radius_gyration_A"] = round(math.sqrt(rg2), 4)
    return desc


def heuristic_seed_params(rec: MoleculeRecord) -> dict[str, Any]:
    """Placeholder screening params so uploads appear in the rank table.

    NOT physics-validated nucleation skill — demoted confidence always.
    """
    d = rec.descriptors
    base = 0.28
    # AgI-like elements bump (still exploratory)
    if d.get("has_silver") and d.get("has_iodine"):
        base = 0.55
        opt = -7.0
        lattice = 0.5
        agent = AgentClass.ICE_NUCLEANT
    elif d.get("n_metals", 0) > 0:
        base = 0.40
        opt = -12.0
        lattice = 0.25
        agent = AgentClass.ICE_NUCLEANT
    elif d.get("frac_polar", 0) > 0.25:
        base = 0.38
        opt = -8.0
        lattice = None
        agent = AgentClass.HYGROSCOPIC
    else:
        base = 0.32
        opt = -15.0
        lattice = 0.15
        agent = AgentClass.ORGANIC

    # size penalty for huge molecules
    if rec.n_atoms > 80:
        base *= 0.7
    density = 1.2
    if d.get("has_silver"):
        density = 5.0
    elif d.get("n_metals", 0):
        density = 3.0

    return {
        "base_efficiency": round(min(0.75, base), 4),
        "optimal_temp_c": opt,
        "lattice_match_score": lattice,
        "density_g_cm3": density,
        "agent_class": agent,
    }


def record_to_candidate(
    rec: MoleculeRecord,
    *,
    name: str | None = None,
    candidate_id: str | None = None,
    notes: str = "",
) -> Candidate:
    seeds = heuristic_seed_params(rec)
    content_key = rec.smiles or rec.formula or str(rec.element_counts)
    cid = candidate_id or slug_id(name or rec.formula or "upload", content_key)
    display = name or rec.formula or cid
    warn = "; ".join(rec.warnings) if rec.warnings else ""
    note = notes or (
        f"Uploaded {rec.format.upper()} → exploratory placeholder efficiency. "
        f"Molecular builder will refine this. {warn}"
    ).strip()
    tags = ["upload", "exploratory", "builder-feed", rec.format]
    if seeds["agent_class"] == AgentClass.ORGANIC:
        tags.append("organic")
    meta = {
        "molecule": rec.as_dict(),
        "placeholder_efficiency": True,
        "builder_ready": True,
    }
    return Candidate(
        id=cid,
        name=display,
        formula=rec.formula,
        agent_class=seeds["agent_class"],
        base_efficiency=float(seeds["base_efficiency"]),
        optimal_temp_c=float(seeds["optimal_temp_c"]),
        lattice_match_score=seeds["lattice_match_score"],
        density_g_cm3=float(seeds["density_g_cm3"]),
        notes=note,
        source="upload",
        tags=tuple(tags),
        meta=meta,
    )


def detect_format(filename: str | None, content: str, explicit: str | None = None) -> str:
    if explicit:
        f = explicit.lower().strip()
        if f in {"smiles", "smi", "xyz", "mol", "sdf", "json"}:
            return "smiles" if f == "smi" else ("mol" if f == "sdf" else f)
        raise ValueError(f"unsupported format: {explicit}")
    if filename:
        low = filename.lower()
        if low.endswith((".smi", ".smiles")):
            return "smiles"
        if low.endswith(".xyz"):
            return "xyz"
        if low.endswith((".mol", ".sdf", ".sd")):
            return "mol"
        if low.endswith(".json"):
            return "json"
    text = content.strip()
    if text.startswith("{") or text.startswith("["):
        return "json"
    # XYZ: first non-empty line is int
    first = text.split("\n", 1)[0].strip()
    if re.fullmatch(r"\d+", first):
        return "xyz"
    # molfile often has V2000
    if "V2000" in text or "V3000" in text:
        return "mol"
    # default short single-line → SMILES
    if "\n" not in text and len(text) < 500:
        return "smiles"
    raise ValueError(
        "could not detect format — pass format=smiles|xyz|mol|json "
        "or use a standard extension"
    )


def parse_upload(
    content: str,
    *,
    filename: str | None = None,
    format: str | None = None,
    name: str | None = None,
    candidate_id: str | None = None,
    notes: str = "",
) -> tuple[MoleculeRecord, Candidate]:
    """Parse upload bytes/text → (MoleculeRecord, Candidate)."""
    if not content or not str(content).strip():
        raise ValueError("empty upload content")
    if len(content) > 5_000_000:
        raise ValueError("upload too large (max 5 MB text)")

    fmt = detect_format(filename, content, format)

    if fmt == "json":
        import json

        data = json.loads(content)
        if isinstance(data, list):
            raise ValueError("JSON array not supported — send one molecule object")
        if not isinstance(data, dict):
            raise ValueError("JSON must be an object")
        # Full candidate pass-through
        if "id" in data and "name" in data and "base_efficiency" in data:
            from ina_sim.library.registry import _candidate_from_dict

            raw = dict(data)
            raw.setdefault("source", "upload")
            tags = list(raw.get("tags") or [])
            for t in ("upload", "exploratory", "builder-feed"):
                if t not in tags:
                    tags.append(t)
            raw["tags"] = tags
            cand = _candidate_from_dict(raw)
            rec = MoleculeRecord(
                format="json",
                formula=cand.formula,
                n_atoms=int((cand.meta or {}).get("n_atoms") or 0),
                smiles=(cand.meta or {}).get("smiles"),
                raw_preview=content[:500],
                descriptors=dict(cand.meta or {}),
            )
            return rec, cand
        # SMILES wrapper
        if "smiles" in data:
            rec = parse_smiles(str(data["smiles"]))
            cand = record_to_candidate(
                rec,
                name=name or data.get("name"),
                candidate_id=candidate_id or data.get("id"),
                notes=notes or str(data.get("notes") or ""),
            )
            return rec, cand
        raise ValueError(
            "JSON needs either full candidate fields "
            "(id, name, base_efficiency, …) or a smiles key"
        )

    if fmt == "smiles":
        rec = parse_smiles(content.strip().splitlines()[0])
    elif fmt == "xyz":
        rec = parse_xyz(content)
    elif fmt == "mol":
        rec = parse_mol(content)
    else:
        raise ValueError(f"unsupported format: {fmt}")

    cand = record_to_candidate(
        rec, name=name, candidate_id=candidate_id, notes=notes
    )
    return rec, cand

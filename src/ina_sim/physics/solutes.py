"""Soluble salts: what they actually do to freezing.

The starter library inherited NaCl, CaCl2 and KI from a supercooled-water
calculator, where they were freezing-point depressants. Carrying them into an
ice nucleation ranking as "ice nucleants" inverts the physics: dissolved salts
lower water activity and depress freezing, they do not nucleate ice
(Koop et al., 2000). KI in particular is a soluble iodide, not silver iodide -
sharing an ion with AgI confers no ice nucleation ability.

So this module scores solutes on their own axis, the colligative freezing point
depression

    dTf = i * Kf * b        Kf = 1.86 K kg mol^-1 (CRC Handbook)

with i the van 't Hoff factor and b the molality. This is the ideal dilute
limit; real electrolytes deviate at high concentration through the osmotic
coefficient, and that deviation is reported rather than absorbed.

Nothing here produces an ns value, because there is nothing to measure: these
species have no ice nucleation active site density.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ina_sim.units import CRYOSCOPIC_CONSTANT_K_KG_PER_MOL

# Ideal (fully dissociated) van 't Hoff factors and molar masses.
# Molar masses: CRC Handbook standard atomic weights.
SOLUTES: dict[str, dict[str, Any]] = {
    "nacl": {
        "name": "sodium chloride",
        "formula": "NaCl",
        "ions": 2,
        "molar_mass_g_per_mol": 58.44,
    },
    "cacl2": {
        "name": "calcium chloride",
        "formula": "CaCl2",
        "ions": 3,
        "molar_mass_g_per_mol": 110.98,
    },
    "ki": {
        "name": "potassium iodide",
        "formula": "KI",
        "ions": 2,
        "molar_mass_g_per_mol": 166.00,
    },
}

# Above this molality the ideal colligative law is no longer quantitative;
# the osmotic coefficient of NaCl departs from 1 by more than ~10% here.
IDEAL_LIMIT_MOLAL = 1.0


@dataclass(frozen=True)
class FreezingPointDepression:
    solute_id: str
    molality_mol_per_kg: float
    van_t_hoff_i: int
    delta_tf_k: float
    freezing_point_c: float
    ideal_limit_exceeded: bool
    reference: str = "crc_handbook"

    def as_dict(self) -> dict[str, Any]:
        return {
            "solute": self.solute_id,
            "molality_mol_per_kg": self.molality_mol_per_kg,
            "van_t_hoff_i": self.van_t_hoff_i,
            "delta_Tf_k": round(self.delta_tf_k, 4),
            "freezing_point_c": round(self.freezing_point_c, 4),
            "ideal_limit_exceeded": self.ideal_limit_exceeded,
            "reference": self.reference,
            "note": (
                "colligative freezing point depression, ideal dilute limit; "
                "this lowers the equilibrium melting point and does not "
                "nucleate ice"
            ),
        }


def is_solute(candidate_id: str) -> bool:
    return candidate_id in SOLUTES


def freezing_point_depression(
    solute_id: str,
    molality_mol_per_kg: float,
) -> FreezingPointDepression:
    """dTf = i * Kf * b for a fully dissociated salt."""
    if solute_id not in SOLUTES:
        raise KeyError(f"no colligative data for {solute_id!r}")
    if molality_mol_per_kg < 0:
        raise ValueError("molality must be non-negative")
    ions = int(SOLUTES[solute_id]["ions"])
    delta = ions * CRYOSCOPIC_CONSTANT_K_KG_PER_MOL * molality_mol_per_kg
    return FreezingPointDepression(
        solute_id=solute_id,
        molality_mol_per_kg=molality_mol_per_kg,
        van_t_hoff_i=ions,
        delta_tf_k=delta,
        freezing_point_c=-delta,
        ideal_limit_exceeded=molality_mol_per_kg > IDEAL_LIMIT_MOLAL,
    )


def mass_fraction_to_molality(mass_fraction: float, molar_mass_g_per_mol: float) -> float:
    """Convert solute mass fraction (0-1) to molality in mol per kg of water."""
    if not 0.0 <= mass_fraction < 1.0:
        raise ValueError("mass_fraction must be in [0, 1)")
    if molar_mass_g_per_mol <= 0:
        raise ValueError("molar mass must be positive")
    grams_solute = mass_fraction * 1000.0
    kg_water = (1.0 - mass_fraction)
    return (grams_solute / molar_mass_g_per_mol) / kg_water


def solute_statement(candidate_id: str) -> str | None:
    """One-line honest description for a soluble salt, or None."""
    if candidate_id not in SOLUTES:
        return None
    body = SOLUTES[candidate_id]
    return (
        f"{body['name']} ({body['formula']}) is a soluble salt: it depresses the "
        f"freezing point colligatively (i={body['ions']}) and lowers water "
        "activity, which suppresses ice nucleation rather than promoting it "
        "(Koop et al. 2000). It has no ice nucleation active site density."
    )

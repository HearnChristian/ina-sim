"""Molecular upload parsing + registry (builder feed)."""

from __future__ import annotations

import json

import pytest

from ina_sim.library.loader import load_candidates
from ina_sim.library.molecular import (
    parse_smiles,
    parse_upload,
    parse_xyz,
)
from ina_sim.library.registry import clear_session, list_session, register, unregister
from ina_sim.models.conditions import Conditions
from ina_sim.screen.rank import rank_candidates


@pytest.fixture(autouse=True)
def _clean_session():
    clear_session(delete_files=False)
    yield
    clear_session(delete_files=False)


def test_parse_smiles_ethanol():
    rec = parse_smiles("CCO")
    assert rec.n_atoms >= 3
    assert rec.element_counts.get("C", 0) >= 2
    assert rec.element_counts.get("O", 0) == 1
    assert rec.formula


def test_parse_smiles_aromatic():
    rec = parse_smiles("c1ccccc1")
    assert rec.element_counts.get("C", 0) == 6


def test_parse_xyz_water():
    xyz = """3
water
O  0.0  0.0  0.0
H  0.96 0.0  0.0
H -0.24 0.93 0.0
"""
    rec = parse_xyz(xyz)
    assert rec.n_atoms == 3
    assert rec.coords is not None
    assert rec.formula in ("H2O", "OH2")


def test_upload_smiles_to_candidate_and_screen():
    rec, cand = parse_upload("CCO", format="smiles", name="Ethanol")
    assert cand.source == "upload"
    assert "exploratory" in cand.tags
    assert "builder-feed" in cand.tags
    register(cand, persist=False)
    assert any(c.id == cand.id for c in list_session())
    # appears when include_uploads
    pool = list(load_candidates(include_uploads=True))
    assert any(c.id == cand.id for c in pool)
    ranked = rank_candidates(pool, Conditions(temperature_c=-10.0))
    assert any(r.candidate.id == cand.id for r in ranked)


def test_upload_json_full_candidate():
    payload = {
        "id": "custom_test_mol",
        "name": "Custom",
        "formula": "C2H6O",
        "agent_class": "organic",
        "base_efficiency": 0.33,
        "optimal_temp_c": -12.0,
        "density_g_cm3": 0.79,
        "tags": ["upload"],
        "notes": "unit test",
    }
    rec, cand = parse_upload(json.dumps(payload), format="json")
    assert cand.id == "custom_test_mol"
    assert cand.base_efficiency == 0.33


def test_detect_bad_smiles():
    with pytest.raises(ValueError):
        parse_smiles("")


def test_unregister():
    _, cand = parse_upload("CC", format="smiles", name="Ethane")
    register(cand, persist=False)
    assert unregister(cand.id, delete_file=False)
    assert all(c.id != cand.id for c in list_session())

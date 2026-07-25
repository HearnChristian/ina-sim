"""Soluble salts are scored on the right axis, and evidence is never invented."""

from __future__ import annotations

import pytest

from ina_sim.library.loader import get_candidate
from ina_sim.models.conditions import Conditions
from ina_sim.physics.evidence import (
    EVIDENCE_MEASURED,
    EVIDENCE_NONE,
    EVIDENCE_SOLUTE,
    evidence_for,
    evidence_summary,
)
from ina_sim.physics.solutes import (
    freezing_point_depression,
    is_solute,
    mass_fraction_to_molality,
    solute_statement,
)
from ina_sim.screen.rank import screen_one


def test_nacl_one_molal_matches_textbook_value():
    """i * Kf * b = 2 * 1.86 * 1 = 3.72 K."""
    result = freezing_point_depression("nacl", 1.0)
    assert result.delta_tf_k == pytest.approx(3.72)
    assert result.freezing_point_c == pytest.approx(-3.72)


def test_calcium_chloride_depresses_more_than_sodium_chloride():
    """Three ions per formula unit instead of two."""
    cacl2 = freezing_point_depression("cacl2", 0.5)
    nacl = freezing_point_depression("nacl", 0.5)
    assert cacl2.delta_tf_k > nacl.delta_tf_k
    assert cacl2.delta_tf_k / nacl.delta_tf_k == pytest.approx(1.5)


def test_depression_is_linear_in_molality():
    a = freezing_point_depression("ki", 0.25).delta_tf_k
    b = freezing_point_depression("ki", 0.50).delta_tf_k
    assert b == pytest.approx(2 * a)


def test_ideal_limit_is_flagged_where_the_law_stops_being_quantitative():
    assert freezing_point_depression("nacl", 0.5).ideal_limit_exceeded is False
    assert freezing_point_depression("nacl", 3.0).ideal_limit_exceeded is True


def test_seawater_is_the_right_order_of_magnitude():
    """~0.6 molal NaCl. Ideal law gives 2.2 K against a measured 1.9 K, so it
    must land close but slightly high - that overestimate is why the ideal
    limit is documented rather than presented as exact."""
    delta = freezing_point_depression("nacl", 0.6).delta_tf_k
    assert 1.9 < delta < 2.5


def test_mass_fraction_conversion():
    # 5.844 g NaCl in 100 g solution -> ~1.05 molal
    molality = mass_fraction_to_molality(0.05844, 58.44)
    assert molality == pytest.approx(1.0 / (1 - 0.05844), rel=1e-3)


def test_unknown_solute_raises():
    with pytest.raises(KeyError):
        freezing_point_depression("agi", 1.0)


def test_negative_molality_rejected():
    with pytest.raises(ValueError):
        freezing_point_depression("nacl", -1.0)


@pytest.mark.parametrize("cid", ["nacl", "cacl2", "ki"])
def test_all_three_salts_are_treated_as_solutes(cid):
    assert is_solute(cid)
    statement = solute_statement(cid)
    assert statement and "no ice nucleation active site density" in statement


def test_potassium_iodide_is_not_classed_as_an_ice_nucleant():
    """KI is a soluble salt. Sharing an iodide ion with AgI proves nothing."""
    ki = get_candidate("ki")
    assert ki.agent_class.value != "ice_nucleant"
    assert "solute" in ki.tags


def test_evidence_for_measured_material():
    block = evidence_for(get_candidate("k_feldspar"), -20.0)
    assert block["evidence"] == EVIDENCE_MEASURED
    assert block["ns"]["value"] > 0
    assert block["ns"]["citation"].startswith("Harrison")
    assert block["observables"]["t50_c"] is not None


def test_evidence_reports_out_of_range_without_a_number():
    block = evidence_for(get_candidate("kaolinite"), -5.0)
    assert block["evidence"] == EVIDENCE_MEASURED
    assert block["ns"]["value"] is None
    assert "outside" in block["statement"]


def test_evidence_for_solute_has_no_ns():
    block = evidence_for(get_candidate("nacl"), -20.0)
    assert block["evidence"] == EVIDENCE_SOLUTE
    assert block["ns"] is None


def test_evidence_for_unmeasured_material_says_so():
    block = evidence_for(get_candidate("inert_surface"), -20.0)
    assert block["evidence"] == EVIDENCE_NONE
    assert block["ns"] is None
    assert "no ice nucleation parameterization" in block["statement"]


def test_evidence_summary_counts_add_up():
    blocks = [
        evidence_for(get_candidate(cid), -20.0)
        for cid in ("agi", "k_feldspar", "nacl", "inert_surface")
    ]
    summary = evidence_summary(blocks)
    assert summary["n_candidates"] == 4
    assert summary["measured"] + summary["solute"] + summary["unmeasured"] == 4
    assert summary["solute"] == 1
    assert summary["unmeasured"] == 1


def test_screen_result_carries_evidence_and_warns_about_solutes():
    result = screen_one(get_candidate("nacl"), Conditions(temperature_c=-20.0))
    assert result.details["evidence"]["evidence"] == EVIDENCE_SOLUTE
    assert any("soluble salt" in w for w in result.warnings)
    row = result.as_row()
    assert row["ns_m2"] is None


def test_screen_row_exposes_ns_for_measured_material():
    result = screen_one(get_candidate("k_feldspar"), Conditions(temperature_c=-20.0))
    row = result.as_row()
    assert row["ns_m2"] > 0
    assert row["ns_units"] == "m^-2"
    assert row["ns_citation"]

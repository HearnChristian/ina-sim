"""Public-research directional cross-reference tests."""

from ina_sim.gui.server import run_screen_payload
from ina_sim.library.loader import filter_candidates
from ina_sim.models.conditions import Conditions
from ina_sim.physics.research_xref import check_ranking, cross_reference_screen
from ina_sim.screen.rank import rank_candidates


def test_xref_pass_at_minus10_starter():
    payload = run_screen_payload(temperature_c=-10.0, starter_set=True)
    lit = payload["literature_xref"]
    assert lit["summary"]["fail"] == 0
    assert lit["summary"]["ok"] is True
    assert payload.get("fingerprint")
    assert payload["fingerprint"].startswith("T=")
    assert "mode=immersion" in payload["fingerprint"]


def test_feldspar_beats_kaolinite_in_xref():
    cands = filter_candidates(tags=["starter-set"])
    ranked = rank_candidates(cands, Conditions(temperature_c=-15.0))
    ids = [r.candidate.id for r in ranked]
    checks = check_ranking(ids, temp_c=-15.0, mode="immersion")
    fk = [c for c in checks if c.id == "feldspar_gt_kaolinite"]
    assert fk and fk[0].status == "pass"


def test_inverted_ranking_fails_xref():
    # Deliberately reverse order
    bad_ids = ["kaolinite", "nacl", "water_control", "k_feldspar", "agi"]
    checks = check_ranking(bad_ids, temp_c=-15.0, mode="immersion")
    fails = [c for c in checks if c.status == "fail"]
    assert any("feldspar" in c.id or "agi" in c.id for c in fails)


def test_cross_reference_screen_shape():
    out = cross_reference_screen(
        ranked_ids=["agi", "k_feldspar", "kaolinite", "nacl", "water_control"],
        temperature_c=-10.0,
        relative_humidity_pct=95.0,
        pressure_hpa=850.0,
        mode="immersion",
        agent_classes={"nacl": "hygroscopic"},
    )
    assert "summary" in out and "checks" in out
    assert out["summary"]["ok"] is True

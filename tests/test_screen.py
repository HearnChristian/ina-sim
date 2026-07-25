from ina_sim.library.loader import filter_candidates, get_candidate, load_candidates
from ina_sim.models.conditions import Conditions
from ina_sim.screen.rank import rank_candidates, screen_one, temperature_sweep


def test_library_loads():
    cands = load_candidates()
    assert len(cands) >= 5
    ids = {c.id for c in cands}
    assert "agi" in ids
    assert "k_feldspar" in ids


def test_agi_beats_control_at_minus7():
    conditions = Conditions(temperature_c=-7.0, relative_humidity_pct=95.0)
    ranked = rank_candidates(list(load_candidates()), conditions)
    ids = [r.candidate.id for r in ranked]
    assert ids.index("agi") < ids.index("water_control")
    assert ids.index("agi") < ids.index("inert_surface")


def test_upload_organic_flagged_exploratory():
    from ina_sim.library.molecular import parse_upload
    from ina_sim.library.registry import clear_session, register

    clear_session(delete_files=False)
    _, cand = parse_upload("CCO", format="smiles", name="Ethanol")
    register(cand, persist=False)
    r = screen_one(cand, Conditions(temperature_c=-15.0))
    assert r.confidence.value == "exploratory"
    clear_session(delete_files=False)


def test_ina_per_kg_proxy_present_for_agi():
    agi = get_candidate("agi")
    r = screen_one(agi, Conditions(temperature_c=-7.0))
    assert r.ina_per_kg_proxy is not None
    assert r.relative_ina_score > 0


def test_screen_includes_cnt_and_pathway():
    agi = get_candidate("agi")
    r = screen_one(agi, Conditions(temperature_c=-10.0, mode="immersion"))
    assert r.details.get("pathway") == "ice_nucleation"
    assert "cnt_score" in r.details
    assert "cnt" in r.details
    assert r.fidelity.startswith("L0+L1")


def test_deposition_mode_warns_without_ice_supersat():
    # warm + low RH → not ice supersaturated
    r = screen_one(
        get_candidate("agi"),
        Conditions(temperature_c=5.0, relative_humidity_pct=50.0, mode="deposition"),
    )
    assert any("ice-supersaturated" in w for w in r.warnings)


def test_temperature_sweep_runs():
    cands = filter_candidates(tags=["starter-set"])
    pts = temperature_sweep(cands, t_min=-20, t_max=-10, step=5.0)
    assert len(pts) == 3
    assert "rankings" in pts[0]
    assert any(x["id"] == "agi" for x in pts[0]["rankings"])

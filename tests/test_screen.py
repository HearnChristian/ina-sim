from ina_sim.library.loader import get_candidate, load_candidates
from ina_sim.models.conditions import Conditions
from ina_sim.screen.rank import rank_candidates, screen_one


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


def test_organic_flagged_exploratory():
    t = get_candidate("testosterone")
    r = screen_one(t, Conditions(temperature_c=-15.0))
    assert r.confidence.value == "exploratory"
    assert any("payload" in w for w in r.warnings)


def test_ina_per_kg_proxy_present_for_agi():
    agi = get_candidate("agi")
    r = screen_one(agi, Conditions(temperature_c=-7.0))
    assert r.ina_per_kg_proxy is not None
    assert r.relative_ina_score > 0

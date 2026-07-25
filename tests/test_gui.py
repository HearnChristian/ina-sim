"""Tests for GUI screen payload + static assets."""

from ina_sim.gui.server import STATIC_DIR, run_screen_payload
from ina_sim.library.loader import filter_candidates
from ina_sim.screen.rank import temperature_sweep


def test_static_index_exists():
    assert (STATIC_DIR / "index.html").is_file()
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert 'type="range"' in html
    assert "Relative score sketch" in html or "score sketch" in html
    # Menus are real dropdowns (not dead labels)
    assert 'data-cmd="export"' in html
    assert 'data-cmd="about"' in html
    # Export / upload are menu-only (not main chrome clutter)
    assert 'id="export"' not in html
    assert "upload-dialog" in html
    assert "Add to library" not in html
    # Optional data-tip system (toggleable), no floating #ttip spam
    assert 'id="ttip"' not in html
    assert "data-tip=" in html
    assert "toggle-tips" in html
    # Professional UI bits
    assert "results-group" in html
    assert "sketch-group" in html
    assert "assumptions" in html
    assert "mechanism_banner" in html
    assert 'id="track"' in html
    assert "Core agents only" in html
    assert "Ice nucleants (INA)" in html


def test_run_screen_payload_starter_set():
    payload = run_screen_payload(temperature_c=-10.0, starter_set=True)
    assert payload["baseline"] == "agi"
    assert "CNT" in payload["fidelity"]
    assert "atmosphere" in payload
    assert payload["atmosphere"]["s_ice"] > 0
    ids = {r["id"] for r in payload["results"]}
    assert "agi" in ids
    assert "k_feldspar" in ids
    assert "water_control" in ids
    assert "testosterone" not in ids
    assert payload["results"][0]["relative_ina"] >= payload["results"][-1]["relative_ina"]
    assert "cnt_score" in payload["results"][0]


def test_run_screen_payload_all_agents():
    payload = run_screen_payload(temperature_c=-7.0, starter_set=False)
    assert len(payload["results"]) >= 5


def test_temperature_sweep_payload_shape():
    cands = filter_candidates(tags=["starter-set"])
    pts = temperature_sweep(cands, t_min=-12, t_max=-8, step=2)
    assert len(pts) >= 2


def test_upload_api_path_via_parse_and_screen():
    from ina_sim.library.molecular import parse_upload
    from ina_sim.library.registry import clear_session, register

    clear_session(delete_files=False)
    _, cand = parse_upload("CCO", format="smiles", name="Ethanol")
    register(cand, persist=False)
    # starter set excludes uploads
    p0 = run_screen_payload(temperature_c=-10.0, starter_set=True)
    assert all(r["id"] != cand.id for r in p0["results"])
    # full library includes uploads
    p1 = run_screen_payload(temperature_c=-10.0, starter_set=False)
    assert any(r["id"] == cand.id for r in p1["results"])
    clear_session(delete_files=False)

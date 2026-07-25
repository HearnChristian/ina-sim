"""Stress tests: extreme inputs, grids, and API clamping robustness."""

from __future__ import annotations

import math

import pytest

from ina_sim.gui.server import run_screen_payload
from ina_sim.library.loader import filter_candidates, load_candidates
from ina_sim.models.conditions import Conditions
from ina_sim.physics.atmosphere import atmosphere_state, saturating_vapor_pressure_hpa
from ina_sim.physics.cnt import cnt_activity_score, cnt_estimate
from ina_sim.physics.efficiency import agent_efficiency
from ina_sim.screen.rank import rank_candidates, screen_one, temperature_sweep


def test_atmosphere_grid_all_finite():
    temps = [-40, -20, -10, -1, 0, 5, 20]
    rhs = [0, 1, 50, 95, 100]
    ps = [200, 500, 850, 1013]
    for t in temps:
        for rh in rhs:
            for p in ps:
                atm = atmosphere_state(float(t), float(rh), float(p), 1e6)
                d = atm.as_dict()
                for k, v in d.items():
                    if isinstance(v, float):
                        assert math.isfinite(v), f"{k} non-finite at T={t} RH={rh} P={p}"


def test_screen_grid_all_finite_and_bounded():
    cands = filter_candidates(tags=["starter-set"])
    temps = [-35, -20, -10, -5, 0, 5]
    modes = ["immersion", "deposition", "contact"]
    for t in temps:
        for mode in modes:
            cond = Conditions(
                temperature_c=float(t),
                relative_humidity_pct=95.0,
                mode=mode,
            )
            ranked = rank_candidates(cands, cond)
            assert ranked
            for r in ranked:
                assert 0.0 <= r.overall_efficiency <= 1.0
                assert math.isfinite(r.relative_ina_score)
                assert r.relative_ina_score >= 0
                if r.ina_per_kg_proxy is not None:
                    assert math.isfinite(r.ina_per_kg_proxy)
                    assert r.ina_per_kg_proxy >= 0


def test_cnt_extreme_supersaturation_finite():
    for s in [1.0, 1.0001, 1.1, 1.5, 2.0, 5.0]:
        est = cnt_estimate(-20.0, s, lattice_match=0.8)
        if s <= 1.0:
            assert not est.valid
        else:
            assert est.valid
            assert math.isfinite(est.delta_g_star_kt)
            assert est.r_star_nm is not None and est.r_star_nm > 0


def test_cnt_activity_score_bounded_grid():
    for t in range(-40, 11, 5):
        for s in [0.5, 1.0, 1.2]:
            sc = cnt_activity_score(float(t), s, 0.5)
            assert 0.0 <= sc <= 1.0


def test_zero_seeding_density_yields_zero_efficiency():
    agi = next(c for c in load_candidates() if c.id == "agi")
    eff = agent_efficiency(
        agi,
        Conditions(temperature_c=-10.0, seeding_density_per_l=0.0),
    )
    assert abs(eff.overall) < 1e-12


def test_conditions_reject_nan_and_inf():
    with pytest.raises(ValueError):
        Conditions(temperature_c=float("nan")).validate()
    with pytest.raises(ValueError):
        Conditions(temperature_c=float("inf")).validate()
    with pytest.raises(ValueError):
        Conditions(relative_humidity_pct=120.0).validate()
    with pytest.raises(ValueError):
        Conditions(pressure_hpa=-1.0).validate()
    with pytest.raises(ValueError):
        Conditions(mode="laser").validate()


def test_conditions_clamped_repairs_gui_extremes():
    c = Conditions(
        temperature_c=-200.0,
        relative_humidity_pct=150.0,
        pressure_hpa=10.0,
        seeding_density_per_l=-5.0,
        particle_diameter_um=1e-6,
    ).clamped()
    c.validate()
    assert c.temperature_c >= -80.0
    assert 0.0 <= c.relative_humidity_pct <= 100.0
    assert c.pressure_hpa >= 50.0
    assert c.seeding_density_per_l >= 0.0
    assert c.particle_diameter_um >= 1e-3


def test_temperature_sweep_auto_coarsens_tiny_step():
    cands = filter_candidates(tags=["starter-set"])
    pts = temperature_sweep(
        cands, t_min=-30, t_max=0, step=0.01, max_points=50
    )
    assert len(pts) <= 55
    assert pts[0]["T_c"] <= pts[-1]["T_c"]


def test_api_payload_clamps_and_survives_extremes():
    p = run_screen_payload(
        temperature_c=-100.0,
        relative_humidity_pct=200.0,
        pressure_hpa=5.0,
        seeding_density_per_l=1e9,
        particle_diameter_um=0.0,
        starter_set=True,
    )
    assert p["results"]
    assert math.isfinite(p["atmosphere"]["s_ice"])
    for r in p["results"]:
        assert math.isfinite(r["relative_ina"])


def test_api_rejects_bad_sort():
    with pytest.raises(ValueError):
        run_screen_payload(sort_key="vibes")


def test_magnus_monotonic_with_temperature():
    prev = saturating_vapor_pressure_hpa(-40.0)
    for t in range(-39, 21):
        e = saturating_vapor_pressure_hpa(float(t))
        assert e > prev
        prev = e


def test_rank_stable_under_repeated_calls():
    cands = filter_candidates(tags=["starter-set"])
    cond = Conditions(temperature_c=-12.0, relative_humidity_pct=96.0)
    a = [r.candidate.id for r in rank_candidates(cands, cond)]
    b = [r.candidate.id for r in rank_candidates(cands, cond)]
    assert a == b

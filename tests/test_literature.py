"""Checks against known atmospheric / ice-nucleation literature facts.

These are *directional / order-of-magnitude* anchors for a learning lab — not
a claim that η matches any specific paper's ns(T) or J values.

References used as anchors:
- Saturation vapor pressure of water near 0 °C ≈ 6.11 hPa (IAPWS / Lide tables)
- Below 0 °C: e_sat,ice < e_sat,supercooled-water
- At fixed vapor when T<0: RH_ice > RH_water
- Homogeneous freezing of pure water droplets ~ −35 to −38 °C (order-of-magnitude)
- K-feldspar is among the most ice-active mineral dusts; often warmer activity
  than kaolinite (Atkinson et al.; Zolles et al. — K-feldspar immersion sites
  active near ~250 K / −23 °C class of experiments; kaolinite typically colder)
- AgI is the classic glaciogenic seeding agent, effective in mixed-phase cold clouds
- Sea salt / NaCl is primarily a CCN / hygroscopic agent, not a strong INA
"""

from __future__ import annotations

from ina_sim.library.loader import filter_candidates, get_candidate, load_candidates
from ina_sim.models.conditions import Conditions
from ina_sim.physics.atmosphere import (
    atmosphere_state,
    dewpoint_c,
    saturating_vapor_pressure_hpa,
    saturating_vapor_pressure_ice_hpa,
)
from ina_sim.physics.cnt import cnt_estimate, heterogeneous_factor
from ina_sim.screen.rank import rank_candidates, screen_one

# --- Atmosphere reference points ---

def test_es_water_near_zero_c_matches_known_value():
    """Lide / common tables: e_s(0 °C) ≈ 6.112 hPa (within ~2%)."""
    e = saturating_vapor_pressure_hpa(0.0)
    assert 6.0 < e < 6.25
    assert abs(e - 6.112) / 6.112 < 0.02


def test_es_water_at_minus10_order_of_magnitude():
    """e_s,w(−10 °C) is roughly 2.6 hPa (Magnus ~2.5–2.8)."""
    e = saturating_vapor_pressure_hpa(-10.0)
    assert 2.3 < e < 3.0


def test_ice_es_less_than_water_when_supercooled():
    for t in (-5.0, -10.0, -20.0, -30.0):
        assert saturating_vapor_pressure_ice_hpa(t) < saturating_vapor_pressure_hpa(t)


def test_rh_ice_exceeds_rh_water_when_supercooled():
    atm = atmosphere_state(-15.0, 90.0, 850.0)
    assert atm.rh_ice_pct > atm.relative_humidity_pct
    assert atm.s_ice > atm.s_water


def test_ice_supersaturation_at_cold_high_rh():
    atm = atmosphere_state(-15.0, 95.0, 850.0)
    assert atm.ice_supersaturated
    assert atm.supercooled


def test_dewpoint_equals_temp_at_100_rh():
    td = dewpoint_c(-10.0, 100.0)
    assert td is not None
    assert abs(td - (-10.0)) < 0.15


def test_dewpoint_none_at_zero_rh():
    assert dewpoint_c(-10.0, 0.0) is None


# --- CNT structure ---

def test_cnt_perfect_wetting_lowers_barrier():
    poor = cnt_estimate(-20.0, 1.3, lattice_match=0.1)
    good = cnt_estimate(-20.0, 1.3, lattice_match=0.95)
    assert poor.valid and good.valid
    assert good.f_hetero < poor.f_hetero
    assert good.delta_g_hetero_kt < poor.delta_g_hetero_kt


def test_heterogeneous_factor_bounds():
    assert 0.0 <= heterogeneous_factor(1.0) <= 0.01
    assert abs(heterogeneous_factor(-1.0) - 1.0) < 1e-9


# --- INA ranking directional literature ---

def _rank_ids(temp_c: float, mode: str = "immersion", rh: float = 95.0) -> list[str]:
    cands = list(load_candidates())
    ranked = rank_candidates(
        cands,
        Conditions(temperature_c=temp_c, relative_humidity_pct=rh, mode=mode),
    )
    return [r.candidate.id for r in ranked]


def test_agi_beats_inert_and_water_control_at_minus10():
    ids = _rank_ids(-10.0)
    assert ids.index("agi") < ids.index("water_control")
    assert ids.index("agi") < ids.index("inert_surface")


def test_k_feldspar_outranks_kaolinite_in_mixed_phase():
    """Literature: K-feldspar is typically more ice-active than kaolinite."""
    for t in (-10.0, -15.0, -20.0):
        ids = _rank_ids(t)
        assert ids.index("k_feldspar") < ids.index("kaolinite"), f"failed at {t}°C"


def test_hygroscopic_nacl_not_top_ice_nucleant_when_cold():
    """Sea salt is a CCN; should not dominate ice ranking at −15 °C immersion."""
    ids = _rank_ids(-15.0)
    ice_ids = ["agi", "k_feldspar"]
    for ice in ice_ids:
        assert ids.index(ice) < ids.index("nacl"), f"{ice} should beat nacl at -15"


def test_water_control_stays_near_bottom_except_extreme_cold_context():
    """Homogeneous-ish control remains weak vs AgI across mixed-phase range."""
    for t in (-5.0, -10.0, -20.0, -30.0):
        r_agi = screen_one(get_candidate("agi"), Conditions(temperature_c=t))
        r_w = screen_one(get_candidate("water_control"), Conditions(temperature_c=t))
        assert r_agi.relative_ina_score > r_w.relative_ina_score * 5


def test_agi_optimal_region_stronger_than_far_from_optimum():
    """AgI library optimal_temp is −7 °C; efficiency should fall off far away."""
    near = screen_one(get_candidate("agi"), Conditions(temperature_c=-7.0))
    far = screen_one(get_candidate("agi"), Conditions(temperature_c=-35.0))
    assert near.overall_efficiency > far.overall_efficiency


def test_deposition_mode_requires_ice_supersaturation_signal():
    dry = screen_one(
        get_candidate("agi"),
        Conditions(temperature_c=-10.0, relative_humidity_pct=40.0, mode="deposition"),
    )
    wet = screen_one(
        get_candidate("agi"),
        Conditions(temperature_c=-10.0, relative_humidity_pct=99.0, mode="deposition"),
    )
    assert wet.overall_efficiency > dry.overall_efficiency
    assert any("ice-supersaturated" in w for w in dry.warnings)


def test_starter_set_covers_literature_baselines():
    ids = {c.id for c in filter_candidates(tags=["starter-set"])}
    assert {"agi", "k_feldspar", "kaolinite", "water_control", "nacl"} <= ids

from ina_sim.physics.atmosphere import (
    air_density_kg_m3,
    atmosphere_state,
    relative_humidity_ice_pct,
    saturating_vapor_pressure_hpa,
    saturating_vapor_pressure_ice_hpa,
    specific_humidity,
    supersaturation_ice,
    total_water_vapor_kg,
)


def test_magnus_reasonable_at_zero():
    e = saturating_vapor_pressure_hpa(0.0)
    assert 5.5 < e < 6.5


def test_ice_es_lower_than_water_when_supercooled():
    t = -15.0
    assert saturating_vapor_pressure_ice_hpa(t) < saturating_vapor_pressure_hpa(t)


def test_rh_ice_higher_than_rh_water_when_supercooled():
    rh_w = 95.0
    rh_i = relative_humidity_ice_pct(-10.0, rh_w)
    assert rh_i > rh_w


def test_ice_supersaturation_at_high_rh_cold():
    s_i = supersaturation_ice(-15.0, 95.0)
    assert s_i > 1.0


def test_air_density_positive():
    rho = air_density_kg_m3(-10.0, 850.0)
    assert 0.5 < rho < 1.5


def test_total_vapor_scales_with_volume():
    a = total_water_vapor_kg(1e6, -5.0, 85.0, 850.0)
    b = total_water_vapor_kg(2e6, -5.0, 85.0, 850.0)
    assert abs(b / a - 2.0) < 1e-9


def test_specific_humidity_increases_with_rh():
    q_low = specific_humidity(-5.0, 50.0, 850.0)
    q_high = specific_humidity(-5.0, 95.0, 850.0)
    assert q_high > q_low


def test_atmosphere_state_flags():
    atm = atmosphere_state(-12.0, 96.0, 850.0, 1e6)
    assert atm.supercooled
    assert atm.ice_supersaturated
    d = atm.as_dict()
    assert "s_ice" in d and d["s_ice"] > 1.0


def test_dewpoint_none_at_zero_rh():
    from ina_sim.physics.atmosphere import dewpoint_c

    assert dewpoint_c(-5.0, 0.0) is None

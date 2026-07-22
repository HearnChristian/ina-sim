from ina_sim.physics.atmosphere import (
    air_density_kg_m3,
    saturating_vapor_pressure_hpa,
    specific_humidity,
    total_water_vapor_kg,
)


def test_magnus_reasonable_at_zero():
    # ~6.1 hPa near 0 °C
    e = saturating_vapor_pressure_hpa(0.0)
    assert 5.5 < e < 6.5


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

"""Unit conversions: the cheapest place to lose an order of magnitude."""

from __future__ import annotations

import math

import pytest

from ina_sim.units import (
    CM2_PER_M2,
    celsius_to_kelvin,
    j_het_cm2s_to_m2s,
    kelvin_to_celsius,
    micrometres_to_metres,
    nanometres_to_metres,
    ns_cm2_to_m2,
    ns_m2_to_cm2,
    sphere_surface_area_m2,
    sphere_volume_m3,
)


def test_celsius_kelvin_round_trip():
    for temp_c in (-38.5, -20.0, 0.0, 15.0):
        assert kelvin_to_celsius(celsius_to_kelvin(temp_c)) == pytest.approx(temp_c)


def test_freezing_point_is_273_15_k():
    assert celsius_to_kelvin(0.0) == pytest.approx(273.15)


def test_ns_conversion_direction():
    """1 site per cm^2 is 10^4 sites per m^2, not 10^-4."""
    assert ns_cm2_to_m2(1.0) == pytest.approx(1e4)
    assert ns_m2_to_cm2(1e4) == pytest.approx(1.0)
    assert CM2_PER_M2 == 1e4


def test_ns_conversion_round_trip():
    for value in (1e-3, 1.0, 6.02e12):
        assert ns_m2_to_cm2(ns_cm2_to_m2(value)) == pytest.approx(value)


def test_rate_conversion_matches_area_conversion():
    assert j_het_cm2s_to_m2s(1.0) == pytest.approx(1e4)


def test_sphere_area_and_volume():
    # A 1 um sphere: area pi*d^2, volume pi*d^3/6.
    d = micrometres_to_metres(1.0)
    assert sphere_surface_area_m2(d) == pytest.approx(math.pi * 1e-12)
    assert sphere_volume_m3(d) == pytest.approx(math.pi * 1e-18 / 6.0)


def test_area_scales_with_square_of_diameter():
    small = sphere_surface_area_m2(nanometres_to_metres(100.0))
    large = sphere_surface_area_m2(nanometres_to_metres(200.0))
    assert large / small == pytest.approx(4.0)


def test_negative_diameter_rejected():
    with pytest.raises(ValueError):
        sphere_surface_area_m2(-1.0)
    with pytest.raises(ValueError):
        sphere_volume_m3(-1.0)

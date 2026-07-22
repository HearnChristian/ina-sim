"""Atmospheric thermodynamics helpers.

Ported from HearnChristian/supercool-water-calculator (index.html JS):

- Magnus-type saturation vapor pressure
- specific humidity from partial pressure
- ideal-gas air density
- cloud-volume water vapor inventory

These estimate *available vapor*, not ice nucleation rates. Keep that
distinction when reporting results.
"""

from __future__ import annotations

import math


def saturating_vapor_pressure_hpa(temp_c: float) -> float:
    """Magnus approximation for saturation vapor pressure over water (hPa).

    Formula used in supercool-water-calculator:
        e_s = 6.112 * exp(17.67 * T / (T + 243.5))
    with T in °C, e_s in hPa (mbar).
    """
    return 6.112 * math.exp((17.67 * temp_c) / (temp_c + 243.5))


def specific_humidity(
    temp_c: float,
    relative_humidity_pct: float,
    pressure_hpa: float,
) -> float:
    """Mass mixing ratio of water vapor (kg/kg dry-ish approx as in legacy).

    Legacy JS:
        actualVaporPressure = (RH/100) * satVaporPressure
        specificHumidity = (0.622 * e) / (P - 0.378 * e)
    """
    e_s = saturating_vapor_pressure_hpa(temp_c)
    e = (relative_humidity_pct / 100.0) * e_s
    denom = pressure_hpa - 0.378 * e
    if denom <= 0:
        raise ValueError("Invalid pressure/humidity combination for specific humidity")
    return (0.622 * e) / denom


def air_density_kg_m3(temp_c: float, pressure_hpa: float) -> float:
    """Ideal-gas density of dry air (kg/m³).

    Legacy: airDensity = (P * 100) / (287.058 * (T + 273.15))
    with P in hPa.
    """
    t_k = temp_c + 273.15
    if t_k <= 0:
        raise ValueError("temperature must be above absolute zero")
    return (pressure_hpa * 100.0) / (287.058 * t_k)


def total_water_vapor_kg(
    cloud_volume_m3: float,
    temp_c: float,
    relative_humidity_pct: float,
    pressure_hpa: float,
) -> float:
    """Rough water-vapor mass inventory in a cloud parcel (kg)."""
    q = specific_humidity(temp_c, relative_humidity_pct, pressure_hpa)
    rho = air_density_kg_m3(temp_c, pressure_hpa)
    return cloud_volume_m3 * rho * q

"""Atmospheric thermodynamics helpers.

Ported from HearnChristian/supercool-water-calculator (index.html JS), then
expanded with ice-phase Magnus, supersaturation ratios, and parcel diagnostics.

These estimate *available vapor / thermodynamic state*, not ice nucleation rates.

Reference checks (order-of-magnitude / teaching accuracy):
- e_s,w(0 °C) ≈ 6.11 hPa (IAPWS / Lide triple-point neighborhood)
- Below 0 °C, e_s,ice < e_s,water (supercooled liquid metastable)
- At fixed vapor content when T<0, RH_ice > RH_water
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ina_sim.physics.validate import (
    clamp_pressure_hpa,
    clamp_rh,
    clamp_temperature_c,
    require_finite,
    safe_div,
)

# Magnus / Tetens-style coefficients (water over liquid; ice form common in met)
# Water: close to August-Roche-Magnus / Alduchov–Eskridge family
_W_A = 6.112  # hPa
_W_B = 17.67
_W_C = 243.5  # °C
# Ice: Murray (1967) style coefficients used widely in atmos codes
_I_A = 6.112
_I_B = 22.46
_I_C = 272.62


def saturating_vapor_pressure_hpa(temp_c: float) -> float:
    """Magnus approximation for saturation vapor pressure over liquid water (hPa).

    e_s,w = 6.112 * exp(17.67 * T / (T + 243.5))   T in °C, e in hPa.
    Lab envelope ~−80…+40 °C; still continuous outside but less accurate.
    """
    t = clamp_temperature_c(temp_c)
    denom = t + _W_C
    if abs(denom) < 1e-9:
        raise ValueError("temperature singularity in Magnus water formula")
    e = _W_A * math.exp((_W_B * t) / denom)
    if not math.isfinite(e) or e < 0:
        raise ValueError(f"non-finite e_sat,water at T={temp_c}")
    return e


def saturating_vapor_pressure_ice_hpa(temp_c: float) -> float:
    """Magnus-type saturation vapor pressure over ice (hPa).

    e_s,i = 6.112 * exp(22.46 * T / (T + 272.62))

    Below 0 °C ice has lower vapor pressure than supercooled water → RH_ice > RH_water
    at the same vapor content (key for deposition / mixed-phase).
    Above 0 °C this form is unphysical as a pure-ice surface; we still return a
    continuous value but atmosphere_state flags supercooled=False.
    """
    t = clamp_temperature_c(temp_c)
    denom = t + _I_C
    if abs(denom) < 1e-9:
        raise ValueError("temperature singularity in Magnus ice formula")
    e = _I_A * math.exp((_I_B * t) / denom)
    if not math.isfinite(e) or e < 0:
        raise ValueError(f"non-finite e_sat,ice at T={temp_c}")
    return e


def vapor_pressure_hpa(temp_c: float, relative_humidity_pct: float) -> float:
    """Actual water vapor partial pressure from RH w.r.t. liquid water."""
    rh = clamp_rh(relative_humidity_pct)
    return (rh / 100.0) * saturating_vapor_pressure_hpa(temp_c)


def relative_humidity_ice_pct(temp_c: float, relative_humidity_pct: float) -> float:
    """RH with respect to ice (%), from RH_water and T.

    RH_i = e / e_s,i * 100 = RH_w * (e_s,w / e_s,i)
    """
    e_w = saturating_vapor_pressure_hpa(temp_c)
    e_i = saturating_vapor_pressure_ice_hpa(temp_c)
    rh = clamp_rh(relative_humidity_pct)
    return rh * safe_div(e_w, e_i, default=0.0)


def supersaturation_water(temp_c: float, relative_humidity_pct: float) -> float:
    """Supersaturation ratio w.r.t. liquid water: S_w = e/e_s,w  (1.0 = saturated)."""
    return clamp_rh(relative_humidity_pct) / 100.0


def supersaturation_ice(temp_c: float, relative_humidity_pct: float) -> float:
    """Supersaturation ratio w.r.t. ice: S_i = e/e_s,i."""
    return relative_humidity_ice_pct(temp_c, relative_humidity_pct) / 100.0


def specific_humidity(
    temp_c: float,
    relative_humidity_pct: float,
    pressure_hpa: float,
) -> float:
    """Mass mixing ratio of water vapor (kg/kg), legacy supercool formula.

    actualVaporPressure = (RH/100) * satVaporPressure
    specificHumidity = (0.622 * e) / (P - 0.378 * e)
    """
    p = clamp_pressure_hpa(pressure_hpa)
    e = vapor_pressure_hpa(temp_c, relative_humidity_pct)
    # Cap vapor pressure slightly below total pressure to avoid singular mixing ratio
    e_cap = min(e, 0.95 * p)
    denom = p - 0.378 * e_cap
    if denom <= 1e-9:
        raise ValueError(
            "Invalid pressure/humidity combination for specific humidity "
            f"(P={p} hPa, e={e} hPa)"
        )
    q = (0.622 * e_cap) / denom
    if not math.isfinite(q) or q < 0:
        raise ValueError("non-finite specific humidity")
    return q


def air_density_kg_m3(temp_c: float, pressure_hpa: float) -> float:
    """Ideal-gas density of dry air (kg/m³).

    airDensity = (P * 100) / (287.058 * (T + 273.15))
    """
    t = clamp_temperature_c(temp_c)
    p = clamp_pressure_hpa(pressure_hpa)
    t_k = t + 273.15
    if t_k <= 1e-6:
        raise ValueError("temperature must be above absolute zero")
    rho = (p * 100.0) / (287.058 * t_k)
    if not math.isfinite(rho) or rho <= 0:
        raise ValueError("non-finite air density")
    return rho


def total_water_vapor_kg(
    cloud_volume_m3: float,
    temp_c: float,
    relative_humidity_pct: float,
    pressure_hpa: float,
) -> float:
    """Rough water-vapor mass inventory in a cloud parcel (kg)."""
    vol = require_finite("cloud_volume_m3", cloud_volume_m3)
    if vol <= 0:
        raise ValueError("cloud_volume_m3 must be positive")
    q = specific_humidity(temp_c, relative_humidity_pct, pressure_hpa)
    rho = air_density_kg_m3(temp_c, pressure_hpa)
    mass = vol * rho * q
    if not math.isfinite(mass) or mass < 0:
        raise ValueError("non-finite vapor mass")
    return mass


def dewpoint_c(temp_c: float, relative_humidity_pct: float) -> float | None:
    """Magnus inverse dew-point approximation (°C) w.r.t. liquid water.

    Returns None when RH is effectively zero (undefined dewpoint).
    """
    rh = clamp_rh(relative_humidity_pct)
    if rh < 1e-6:
        return None
    e = vapor_pressure_hpa(temp_c, rh)
    if e <= 1e-12:
        return None
    # invert e = 6.112 * exp(17.67 T_d / (T_d + 243.5))
    ratio = e / _W_A
    if ratio <= 0:
        return None
    gamma = math.log(ratio)
    denom = _W_B - gamma
    if abs(denom) < 1e-12:
        return None
    td = (_W_C * gamma) / denom
    if not math.isfinite(td):
        return None
    return td


@dataclass(frozen=True)
class AtmosphereState:
    """Snapshot of parcel thermodynamics used by the GUI / screen details."""

    temperature_c: float
    relative_humidity_pct: float
    pressure_hpa: float
    e_hpa: float
    e_sat_water_hpa: float
    e_sat_ice_hpa: float
    rh_ice_pct: float
    s_water: float
    s_ice: float
    specific_humidity_kg_kg: float
    air_density_kg_m3: float
    vapor_mass_kg: float
    dewpoint_c: float | None
    supercooled: bool
    ice_supersaturated: bool

    def as_dict(self) -> dict:
        return {
            "temperature_c": self.temperature_c,
            "relative_humidity_pct": self.relative_humidity_pct,
            "pressure_hpa": self.pressure_hpa,
            "e_hpa": round(self.e_hpa, 4),
            "e_sat_water_hpa": round(self.e_sat_water_hpa, 4),
            "e_sat_ice_hpa": round(self.e_sat_ice_hpa, 4),
            "rh_ice_pct": round(self.rh_ice_pct, 2),
            "s_water": round(self.s_water, 4),
            "s_ice": round(self.s_ice, 4),
            "specific_humidity_kg_kg": round(self.specific_humidity_kg_kg, 6),
            "air_density_kg_m3": round(self.air_density_kg_m3, 4),
            "vapor_mass_kg": round(self.vapor_mass_kg, 3),
            "dewpoint_c": (
                None if self.dewpoint_c is None else round(self.dewpoint_c, 2)
            ),
            "supercooled": self.supercooled,
            "ice_supersaturated": self.ice_supersaturated,
        }


def atmosphere_state(
    temp_c: float,
    relative_humidity_pct: float,
    pressure_hpa: float,
    cloud_volume_m3: float = 1e6,
) -> AtmosphereState:
    """Build a full thermo snapshot for a parcel."""
    t = clamp_temperature_c(temp_c)
    rh = clamp_rh(relative_humidity_pct)
    p = clamp_pressure_hpa(pressure_hpa)
    e_w = saturating_vapor_pressure_hpa(t)
    e_i = saturating_vapor_pressure_ice_hpa(t)
    e = vapor_pressure_hpa(t, rh)
    s_w = supersaturation_water(t, rh)
    s_i = supersaturation_ice(t, rh)
    rh_i = relative_humidity_ice_pct(t, rh)
    q = specific_humidity(t, rh, p)
    rho = air_density_kg_m3(t, p)
    vol = require_finite("cloud_volume_m3", cloud_volume_m3)
    if vol <= 0:
        raise ValueError("cloud_volume_m3 must be positive")
    vapor = vol * rho * q
    return AtmosphereState(
        temperature_c=t,
        relative_humidity_pct=rh,
        pressure_hpa=p,
        e_hpa=e,
        e_sat_water_hpa=e_w,
        e_sat_ice_hpa=e_i,
        rh_ice_pct=rh_i,
        s_water=s_w,
        s_ice=s_i,
        specific_humidity_kg_kg=q,
        air_density_kg_m3=rho,
        vapor_mass_kg=vapor,
        dewpoint_c=dewpoint_c(t, rh),
        supercooled=t < 0.0,
        ice_supersaturated=s_i > 1.0,
    )

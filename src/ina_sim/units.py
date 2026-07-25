"""Explicit units for every empirical quantity.

The literature mixes cm^-2 with m^-2, Celsius with kelvin, and per-area with
per-volume rate coefficients. Mixing them silently is the single easiest way to
publish a wrong number, so conversions live here, are named after what they
convert, and are unit-tested against known identities.

Convention used everywhere else in the package:
    * temperatures in function arguments are Celsius unless the name ends _k
    * ns is stored internally in m^-2 (SI)
    * areas in m^2, volumes in m^3, diameters in metres unless named _um / _nm
"""

from __future__ import annotations

import math

KELVIN_OFFSET = 273.15
"""0 C in kelvin. Note the ice-nucleation literature also uses 273.16 (triple
point) and 273.2; differences of 0.05 K are far below the uncertainty of any
ns(T) fit but matter when reproducing a source equation exactly."""

CM2_PER_M2 = 1.0e4
"""1 m^2 = 10^4 cm^2, so ns[m^-2] = ns[cm^-2] * 10^4."""

CM3_PER_M3 = 1.0e6

# Cryoscopic constant of water (CRC Handbook): freezing point depression per
# molal concentration of dissolved particles.
CRYOSCOPIC_CONSTANT_K_KG_PER_MOL = 1.86


def celsius_to_kelvin(temp_c: float) -> float:
    return temp_c + KELVIN_OFFSET


def kelvin_to_celsius(temp_k: float) -> float:
    return temp_k - KELVIN_OFFSET


def ns_cm2_to_m2(ns_cm2: float) -> float:
    """Active site density from cm^-2 to m^-2."""
    return ns_cm2 * CM2_PER_M2


def ns_m2_to_cm2(ns_m2: float) -> float:
    return ns_m2 / CM2_PER_M2


def j_het_cm2s_to_m2s(j_cm2s: float) -> float:
    """Heterogeneous nucleation rate coefficient, cm^-2 s^-1 -> m^-2 s^-1."""
    return j_cm2s * CM2_PER_M2


def j_hom_cm3s_to_m3s(j_cm3s: float) -> float:
    """Homogeneous nucleation rate coefficient, cm^-3 s^-1 -> m^-3 s^-1."""
    return j_cm3s * CM3_PER_M3


def sphere_surface_area_m2(diameter_m: float) -> float:
    """Geometric surface area of a sphere of the given diameter."""
    if diameter_m < 0:
        raise ValueError("diameter must be non-negative")
    return math.pi * diameter_m * diameter_m


def sphere_volume_m3(diameter_m: float) -> float:
    if diameter_m < 0:
        raise ValueError("diameter must be non-negative")
    return math.pi * diameter_m**3 / 6.0


def micrometres_to_metres(value_um: float) -> float:
    return value_um * 1e-6


def nanometres_to_metres(value_nm: float) -> float:
    return value_nm * 1e-9


def litres_to_m3(value_l: float) -> float:
    return value_l * 1e-3


def per_m3_to_per_litre(value_per_m3: float) -> float:
    return value_per_m3 * 1e-3

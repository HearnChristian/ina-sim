"""Droplet-freezing observables: bounds, inversions and the physics of the sign.

Most of these are invariants rather than fixed numbers: a frozen fraction can
never leave [0, 1], a smaller particle must freeze colder, and a slower cooling
ramp must freeze warmer. Getting any of those backwards is a physics bug that a
single golden value would not catch.
"""

from __future__ import annotations

import math

import pytest

from ina_sim.physics.freezing import (
    LN2,
    freezing_curve,
    frozen_fraction_singular,
    frozen_fraction_stochastic,
    inp_concentration_per_m3,
    median_freezing_temperature,
    ns_from_frozen_fraction,
    stochastic_freezing_curve,
)
from ina_sim.physics.ns import get_parameterization
from ina_sim.units import micrometres_to_metres, sphere_surface_area_m2, sphere_volume_m3

KF = get_parameterization("k_feldspar_harrison2019")
HOM = get_parameterization("water_homogeneous_murray2010")
AREA_1UM = sphere_surface_area_m2(micrometres_to_metres(1.0))


@pytest.mark.parametrize("ns", [0.0, 1.0, 1e6, 1e12, 1e20])
@pytest.mark.parametrize("area", [1e-14, 1e-12, 1e-6])
def test_frozen_fraction_stays_in_unit_interval(ns, area):
    assert 0.0 <= frozen_fraction_singular(ns, area) <= 1.0


def test_frozen_fraction_is_zero_without_sites():
    assert frozen_fraction_singular(0.0, AREA_1UM) == 0.0


def test_frozen_fraction_saturates_rather_than_overflowing():
    assert frozen_fraction_singular(1e300, AREA_1UM) == 1.0


def test_frozen_fraction_increases_with_ns_and_with_area():
    assert frozen_fraction_singular(1e11, AREA_1UM) > frozen_fraction_singular(1e10, AREA_1UM)
    assert frozen_fraction_singular(1e11, 2 * AREA_1UM) > frozen_fraction_singular(1e11, AREA_1UM)


@pytest.mark.parametrize("ns", [1e8, 1e10, 5e11])
def test_vali_inversion_round_trip(ns):
    frozen = frozen_fraction_singular(ns, AREA_1UM)
    assert ns_from_frozen_fraction(frozen, AREA_1UM) == pytest.approx(ns, rel=1e-9)


def test_half_frozen_corresponds_to_ln2_sites():
    ns = ns_from_frozen_fraction(0.5, AREA_1UM)
    assert ns * AREA_1UM == pytest.approx(LN2)


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 1.5])
def test_inversion_refuses_undefined_frozen_fractions(bad):
    with pytest.raises(ValueError):
        ns_from_frozen_fraction(bad, AREA_1UM)


def test_inp_concentration_never_exceeds_particle_number():
    n_particles = 1e6
    for ns in (1e6, 1e12, 1e18):
        inp = inp_concentration_per_m3(ns, n_particles, micrometres_to_metres(1.0))
        assert 0.0 <= inp <= n_particles


def test_inp_concentration_matches_linear_limit_when_sites_are_sparse():
    """For ns*A << 1 the exact form must reduce to N * ns * A."""
    n_particles = 1e6
    diameter = micrometres_to_metres(1.0)
    ns = 1e6
    exact = inp_concentration_per_m3(ns, n_particles, diameter)
    linear = n_particles * ns * sphere_surface_area_m2(diameter)
    assert exact == pytest.approx(linear, rel=1e-4)


def test_t50_is_colder_for_smaller_particles():
    """Less surface area means fewer sites, so freezing needs more supercooling."""
    big = median_freezing_temperature(KF, sphere_surface_area_m2(micrometres_to_metres(5.0)))
    small = median_freezing_temperature(KF, sphere_surface_area_m2(micrometres_to_metres(0.5)))
    assert big is not None and small is not None
    assert small < big


def test_t50_returns_none_outside_the_fitted_range():
    # A vanishingly small particle would need ns beyond anything the fit covers.
    assert median_freezing_temperature(KF, sphere_surface_area_m2(1e-9)) is None
    # A huge surface area is already past half-frozen at the warm end.
    assert median_freezing_temperature(KF, 1.0) is None


def test_t50_agrees_with_the_curve_it_came_from():
    t50 = median_freezing_temperature(KF, AREA_1UM)
    curve = freezing_curve(KF, droplet_surface_area_m2=AREA_1UM, step_c=0.05)
    crossing = next(p.temperature_c for p in curve if p.frozen_fraction >= 0.5)
    assert crossing == pytest.approx(t50, abs=0.1)


def test_freezing_curve_is_monotonic_and_bounded():
    curve = freezing_curve(KF, droplet_surface_area_m2=AREA_1UM, step_c=1.0)
    fractions = [p.frozen_fraction for p in curve]
    assert all(0.0 <= f <= 1.0 for f in fractions)
    assert fractions == sorted(fractions), "frozen fraction must rise as T falls"


def test_freezing_curve_band_brackets_the_central_curve():
    for point in freezing_curve(KF, droplet_surface_area_m2=AREA_1UM, step_c=2.0):
        assert point.frozen_fraction_low <= point.frozen_fraction <= point.frozen_fraction_high


def test_stochastic_step_matches_hand_computation():
    # 1 - exp(-(J*sigma) * dt) with J = 1e5 cm^-2 s^-1, sigma = 1e-8 cm^2, dt = 60 s
    got = frozen_fraction_stochastic(
        j_het_cm2_s=1e5, particle_area_cm2=1e-8, dt_s=60.0
    )
    assert got == pytest.approx(1.0 - math.exp(-0.06))


def test_stochastic_freezing_is_slower_for_shorter_dwell():
    fast = frozen_fraction_stochastic(j_het_cm2_s=1e5, particle_area_cm2=1e-8, dt_s=1.0)
    slow = frozen_fraction_stochastic(j_het_cm2_s=1e5, particle_area_cm2=1e-8, dt_s=60.0)
    assert slow > fast


def test_slower_cooling_freezes_warmer():
    """The signature of a rate process: more time at temperature means more ice."""
    volume = sphere_volume_m3(micrometres_to_metres(10.0))

    def t50(rate_k_per_min: float) -> float:
        curve = stochastic_freezing_curve(
            None,
            particle_area_m2=0.0,
            droplet_volume_m3=volume,
            hom_param=HOM,
            cooling_rate_k_per_min=rate_k_per_min,
            t_start_c=HOM.t_max_c,
            t_end_c=HOM.t_min_c,
            step_c=0.01,
        )
        return next(p["T_c"] for p in curve if p["frozen_fraction"] >= 0.5)

    assert t50(0.1) > t50(10.0)


def test_stochastic_curve_frozen_fraction_is_monotonic():
    rows = stochastic_freezing_curve(
        None,
        particle_area_m2=0.0,
        droplet_volume_m3=sphere_volume_m3(micrometres_to_metres(10.0)),
        hom_param=HOM,
        cooling_rate_k_per_min=1.0,
        t_start_c=HOM.t_max_c,
        t_end_c=HOM.t_min_c,
        step_c=0.05,
    )
    fractions = [r["frozen_fraction"] for r in rows]
    assert fractions == sorted(fractions)
    assert 0.0 <= fractions[-1] <= 1.0


def test_singular_curve_rejects_a_rate_parameterization():
    with pytest.raises(ValueError):
        freezing_curve(HOM, droplet_surface_area_m2=AREA_1UM)


def test_bad_inputs_are_rejected():
    with pytest.raises(ValueError):
        frozen_fraction_singular(-1.0, AREA_1UM)
    with pytest.raises(ValueError):
        median_freezing_temperature(KF, 0.0)
    with pytest.raises(ValueError):
        stochastic_freezing_curve(
            None,
            particle_area_m2=0.0,
            droplet_volume_m3=1e-15,
            hom_param=HOM,
            cooling_rate_k_per_min=0.0,
            t_start_c=-36.5,
            t_end_c=-38.0,
        )

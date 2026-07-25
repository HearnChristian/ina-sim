"""Polydisperse aerosol: moments, integration limits and the linear fallacy.

The analytic Hatch-Choate moments give an independent check on the numerical
integration, so the two must agree; and the exact INP integral must reduce to
the familiar ns x surface area only where that approximation is actually valid.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from ina_sim.physics.aerosol import (
    LognormalMode,
    SizeDistribution,
    inp_concentration,
    inp_spectrum,
    parse_mode,
)
from ina_sim.physics.freezing import inp_concentration_per_m3
from ina_sim.physics.ns import evaluate, get_parameterization
from ina_sim.units import micrometres_to_metres, sphere_surface_area_m2

REPO_ROOT = Path(__file__).resolve().parents[1]
DUST = get_parameterization("desert_dust_niemand2012")
KF = get_parameterization("k_feldspar_harrison2019")


def accumulation(**kw) -> LognormalMode:
    body = {"number_per_cm3": 1.0, "median_diameter_um": 0.8, "geometric_sd": 1.9}
    body.update(kw)
    return LognormalMode(**body)


# --- Mode arithmetic -------------------------------------------------------


def test_hatch_choate_second_moment():
    """<D^2> = D_g^2 exp(2 ln^2 sigma_g)."""
    mode = accumulation()
    ln_sd = math.log(mode.geometric_sd)
    expected = mode.median_diameter_m**2 * math.exp(2 * ln_sd**2)
    assert mode.moment(2) == pytest.approx(expected, rel=1e-12)


def test_surface_area_matches_numerical_integration():
    """Analytic moment and binned integral must agree to well under 1%."""
    dist = SizeDistribution(modes=(accumulation(),))
    analytic = dist.modes[0].surface_area_m2_per_m3
    numeric = sum(
        n * sphere_surface_area_m2(d) for d, n in dist.bins(2000)
    )
    assert numeric == pytest.approx(analytic, rel=2e-3)


def test_binned_number_integrates_to_the_stated_concentration():
    dist = SizeDistribution(modes=(accumulation(number_per_cm3=3.0),))
    total = sum(n for _, n in dist.bins(2000))
    assert total == pytest.approx(3.0e6, rel=2e-3)


def test_wider_distribution_has_more_surface_area_at_fixed_number():
    narrow = accumulation(geometric_sd=1.2).surface_area_m2_per_m3
    wide = accumulation(geometric_sd=2.2).surface_area_m2_per_m3
    assert wide > narrow


def test_modes_add():
    a, b = accumulation(), accumulation(number_per_cm3=0.01, median_diameter_um=4.0)
    dist = SizeDistribution(modes=(a, b))
    assert dist.surface_area_m2_per_m3() == pytest.approx(
        a.surface_area_m2_per_m3 + b.surface_area_m2_per_m3, rel=1e-9
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"number_per_cm3": -1.0},
        {"median_diameter_um": 0.0},
        {"geometric_sd": 1.0},
        {"geometric_sd": 0.5},
    ],
)
def test_impossible_modes_are_rejected(kwargs):
    with pytest.raises(ValueError):
        accumulation(**kwargs)


def test_distribution_needs_a_mode():
    with pytest.raises(ValueError):
        SizeDistribution(modes=())


def test_truncation_removes_particles():
    full = SizeDistribution(modes=(accumulation(),))
    coarse_only = SizeDistribution(modes=(accumulation(),), d_min_um=2.0)
    assert coarse_only.total_number_per_m3() < full.total_number_per_m3()
    assert coarse_only.surface_area_m2_per_m3() < full.surface_area_m2_per_m3()


def test_truncation_limits_must_be_ordered():
    with pytest.raises(ValueError):
        SizeDistribution(modes=(accumulation(),), d_min_um=5.0, d_max_um=1.0)


# --- INP concentration -----------------------------------------------------


def test_matches_the_monodisperse_helper_for_a_narrow_mode():
    """A very narrow lognormal is monodisperse; both code paths must agree."""
    diameter_um = 1.0
    mode = LognormalMode(
        number_per_cm3=1.0, median_diameter_um=diameter_um, geometric_sd=1.001
    )
    est = evaluate(DUST, -20.0)
    poly = inp_concentration(SizeDistribution(modes=(mode,)), est, n_bins=400)
    mono = inp_concentration_per_m3(
        est.value, 1.0e6, micrometres_to_metres(diameter_um)
    )
    assert poly.n_inp_per_litre * 1e3 == pytest.approx(mono, rel=1e-3)


def test_linear_approximation_holds_in_the_dilute_limit():
    """Where ns*A << 1 the exact integral must reduce to ns x S_tot."""
    dist = SizeDistribution(modes=(accumulation(median_diameter_um=0.1),))
    est = evaluate(DUST, -13.0)  # small ns, small particles
    result = inp_concentration(dist, est)
    assert result.linear_ratio == pytest.approx(1.0, abs=0.02)


def test_linear_approximation_overstates_when_particles_are_saturated():
    """Big particles at cold temperature carry many sites each; the linear form
    then counts one particle several times."""
    dist = SizeDistribution(modes=(accumulation(median_diameter_um=5.0),))
    result = inp_concentration(dist, evaluate(DUST, -35.0))
    assert result.linear_ratio > 1.5
    assert result.n_inp_linear_per_litre > result.n_inp_per_litre
    assert any("double counts" in n for n in result.notes)


def test_inp_never_exceeds_the_particles_present():
    dist = SizeDistribution(modes=(accumulation(),))
    for temp in (-12.0, -20.0, -30.0, -36.0):
        result = inp_concentration(dist, evaluate(DUST, temp))
        assert result.n_inp_per_litre <= dist.total_number_per_m3() * 1e-3 * 1.000001
        assert 0.0 <= result.activated_fraction <= 1.0


def test_inp_rises_as_temperature_falls():
    dist = SizeDistribution(modes=(accumulation(),))
    warm = inp_concentration(dist, evaluate(DUST, -15.0))
    cold = inp_concentration(dist, evaluate(DUST, -30.0))
    assert cold.n_inp_per_litre > warm.n_inp_per_litre


def test_inp_scales_linearly_with_particle_number():
    est = evaluate(DUST, -20.0)
    one = inp_concentration(SizeDistribution(modes=(accumulation(),)), est)
    ten = inp_concentration(
        SizeDistribution(modes=(accumulation(number_per_cm3=10.0),)), est
    )
    assert ten.n_inp_per_litre == pytest.approx(10 * one.n_inp_per_litre, rel=1e-6)


def test_inp_follows_surface_area_not_particle_number():
    """The lesson of the whole module: INP tracks surface area, and area goes as
    d^2, so a mode's share of the ice nucleation is its share of the area - not
    its share of the count."""
    fine = accumulation(number_per_cm3=100.0, median_diameter_um=0.2)
    coarse = accumulation(
        number_per_cm3=0.1, median_diameter_um=4.0, geometric_sd=2.0
    )
    est = evaluate(DUST, -20.0)

    fine_only = inp_concentration(SizeDistribution(modes=(fine,)), est)
    coarse_only = inp_concentration(SizeDistribution(modes=(coarse,)), est)

    # 1000x fewer coarse particles, yet they supply a comparable INP number
    # because each carries 400x the surface area.
    number_ratio = fine.number_per_cm3 / coarse.number_per_cm3
    inp_ratio = fine_only.n_inp_per_litre / coarse_only.n_inp_per_litre
    area_ratio = fine.surface_area_m2_per_m3 / coarse.surface_area_m2_per_m3
    assert number_ratio == pytest.approx(1000.0)
    assert inp_ratio == pytest.approx(area_ratio, rel=0.15)
    assert inp_ratio < 5.0

    # The residual gap is not noise: the coarse mode is partly saturated, so it
    # yields fewer INP than its area alone implies. That shortfall is exactly
    # the per-mode linear_ratio, which makes the relation an identity.
    assert coarse_only.linear_ratio > fine_only.linear_ratio
    # rel=1e-3 rather than exact: area_ratio here uses the analytic moment
    # while linear_ratio uses the binned integral, so the identity is limited
    # by the binning resolution checked above.
    assert inp_ratio == pytest.approx(
        area_ratio * coarse_only.linear_ratio / fine_only.linear_ratio, rel=1e-3
    )


def test_coarse_mode_dominates_once_it_carries_the_surface_area():
    dist = SizeDistribution(
        modes=(
            accumulation(number_per_cm3=100.0, median_diameter_um=0.2),
            accumulation(number_per_cm3=1.0, median_diameter_um=4.0, geometric_sd=2.0),
        )
    )
    result = inp_concentration(dist, evaluate(DUST, -20.0))
    assert result.fraction_from_coarse > 0.5
    assert result.d50_contribution_um > 1.0


def test_band_brackets_the_central_concentration():
    result = inp_concentration(
        SizeDistribution(modes=(accumulation(),)), evaluate(DUST, -20.0)
    )
    assert result.n_inp_low_per_litre < result.n_inp_per_litre < result.n_inp_high_per_litre


def test_out_of_range_temperature_returns_nothing():
    assert inp_concentration(
        SizeDistribution(modes=(accumulation(),)), evaluate(DUST, -5.0)
    ) is None


def test_rate_parameterization_is_refused():
    kaolinite = get_parameterization("kaolinite_murray2011")
    with pytest.raises(ValueError, match="rate coefficient"):
        inp_concentration(
            SizeDistribution(modes=(accumulation(),)), evaluate(kaolinite, -30.0)
        )


def test_full_truncation_is_an_error_not_a_zero():
    dist = SizeDistribution(modes=(accumulation(),), d_min_um=1000.0)
    with pytest.raises(ValueError, match="exclude the entire size distribution"):
        inp_concentration(dist, evaluate(DUST, -20.0))


def test_spectrum_stays_inside_the_fitted_range():
    dist = SizeDistribution(modes=(accumulation(),))
    rows = inp_spectrum(dist, DUST, step_c=2.0)
    assert rows
    assert all(DUST.t_min_c <= r.temperature_c <= DUST.t_max_c for r in rows)
    concentrations = [r.n_inp_per_litre for r in rows]
    assert concentrations == sorted(concentrations)


# --- Mode parsing ----------------------------------------------------------


def test_parse_mode_round_trip():
    mode = parse_mode("1.5:0.8:1.9:accumulation")
    assert (mode.number_per_cm3, mode.median_diameter_um, mode.geometric_sd) == (
        1.5,
        0.8,
        1.9,
    )
    assert mode.name == "accumulation"


@pytest.mark.parametrize("spec", ["1.0:0.8", "a:b:c", ""])
def test_bad_mode_specs_explain_the_format(spec):
    with pytest.raises(ValueError):
        parse_mode(spec)


# --- CLI -------------------------------------------------------------------


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ina_sim", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_cli_aerosol_json():
    proc = _cli(
        "aerosol",
        "--id",
        "desert_dust_niemand2012",
        "--temp",
        "-20",
        "--mode",
        "1.0:0.8:1.9",
        "--json",
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["results"][0]["n_inp_per_litre"] > 0
    assert payload["distribution"]["surface_area_m2_per_m3"] > 0


def test_cli_aerosol_refuses_a_rate_parameterization():
    proc = _cli(
        "aerosol", "--id", "kaolinite_murray2011", "--mode", "1:1:1.5", "--temp", "-30"
    )
    assert proc.returncode == 1
    assert "rate coefficient" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_cli_aerosol_reports_out_of_range_plainly():
    proc = _cli(
        "aerosol", "--id", "desert_dust_niemand2012", "--mode", "1:1:1.5", "--temp", "-5"
    )
    assert proc.returncode == 0
    assert "outside the fitted range" in proc.stdout

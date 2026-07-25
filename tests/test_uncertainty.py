"""Monte Carlo propagation: reproducible, statistically correct, honest.

The headline check is that when only ns varies, the sampled spread of
log10(n_INP) reproduces the parameterization's own sigma. If that holds, the
machinery is propagating the stated uncertainty rather than inventing one.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from ina_sim.physics.ns import get_parameterization
from ina_sim.physics.uncertainty import Uncertain, propagate_inp

REPO_ROOT = Path(__file__).resolve().parents[1]
DUST = get_parameterization("desert_dust_niemand2012")
KF = get_parameterization("k_feldspar_harrison2019")


def run(param=DUST, **kw):
    body = {
        "temperature_c": -20.0,
        "number_per_cm3": 1.0,
        "median_diameter_um": 0.8,
        "samples": 1500,
    }
    body.update(kw)
    return propagate_inp(param, **body)


def stdev_log10(values: list[float]) -> float:
    logs = [math.log10(v) for v in values if v > 0]
    mean = sum(logs) / len(logs)
    return math.sqrt(sum((v - mean) ** 2 for v in logs) / (len(logs) - 1))


# --- Distribution shapes ---------------------------------------------------


def test_ns_sigma_is_reproduced_when_only_ns_varies():
    """The central correctness check: with everything else fixed and particles
    small enough to be in the dilute limit, the sampled spread of log10(n_INP)
    must equal the fit's own sigma."""
    result = run(
        param=KF,
        median_diameter_um=0.2,
        temperature_sigma_k=0.0,
        number_relative_sigma=0.0,
        diameter_relative_sigma=0.0,
        samples=6000,
    )
    assert stdev_log10(result.values) == pytest.approx(KF.sigma_log10, rel=0.06)


def test_no_uncertainty_at_all_collapses_to_a_point():
    result = run(
        temperature_sigma_k=0.0,
        number_relative_sigma=0.0,
        diameter_relative_sigma=0.0,
        param=get_parameterization("plagioclase_harrison2019"),
        temperature_c=-25.0,
    )
    spread = max(result.values) - min(result.values)
    assert spread > 0  # ns sigma is stated and non-zero
    frozen = stdev_log10(result.values)
    assert frozen == pytest.approx(0.5, rel=0.08)  # plagioclase sigma


def test_percentiles_are_ordered():
    body = run().as_dict()["n_inp_per_litre"]
    assert body["p05"] < body["p16"] < body["p50"] < body["p84"] < body["p95"]


def test_spread_is_reported_in_decades():
    result = run()
    assert result.spread_decades == pytest.approx(
        math.log10(result.percentile(0.95) / result.percentile(0.05)), rel=1e-9
    )


def test_wider_input_uncertainty_gives_a_wider_output():
    tight = run(temperature_sigma_k=0.1, number_relative_sigma=0.05)
    loose = run(temperature_sigma_k=2.0, number_relative_sigma=0.8)
    assert loose.spread_decades > tight.spread_decades


# --- Reproducibility -------------------------------------------------------


def test_same_seed_gives_identical_numbers():
    a, b = run(seed=7), run(seed=7)
    assert a.values == b.values
    assert a.as_dict() == b.as_dict()


def test_different_seeds_differ_but_agree_statistically():
    a, b = run(seed=1, samples=4000), run(seed=2, samples=4000)
    assert a.values != b.values
    assert math.log10(a.median / b.median) == pytest.approx(0.0, abs=0.15)


def test_seed_is_reported_so_a_result_can_be_reproduced():
    assert run(seed=99).as_dict()["seed"] == 99


# --- Exceedance probability ------------------------------------------------


def test_exceedance_falls_as_the_threshold_rises():
    result = run()
    probs = [result.exceedance(t) for t in (0.01, 0.1, 1.0, 10.0, 100.0)]
    assert probs == sorted(probs, reverse=True)
    assert all(0.0 <= p <= 1.0 for p in probs)


def test_exceedance_at_the_median_is_one_half():
    result = run(samples=4000)
    assert result.exceedance(result.median) == pytest.approx(0.5, abs=0.02)


def test_threshold_appears_in_the_payload_only_when_asked():
    assert "probability_above_threshold" not in run().as_dict()
    assert "probability_above_threshold" in run(threshold_per_litre=1.0).as_dict()


# --- Variance decomposition ------------------------------------------------


def test_shares_are_bounded_and_roughly_complete():
    shares = run(samples=4000).variance_share
    assert set(shares) == {
        "ns(T) parameterization",
        "temperature",
        "aerosol number",
        "median diameter",
    }
    assert all(0.0 <= v <= 1.0 for v in shares.values())
    # First-order shares of a near-additive log response should nearly fill 1.
    assert 0.85 <= sum(shares.values()) <= 1.15


def test_parameterization_dominates_when_its_sigma_is_large():
    """The finding that matters: with a 1-decade ns uncertainty, improving your
    aerosol instrument is close to pointless."""
    shares = run(samples=4000).variance_share
    assert shares["ns(T) parameterization"] > 0.8
    assert shares["aerosol number"] < 0.1


def test_temperature_share_grows_with_temperature_uncertainty():
    low = run(samples=4000, temperature_sigma_k=0.1).variance_share["temperature"]
    high = run(samples=4000, temperature_sigma_k=3.0).variance_share["temperature"]
    assert high > low * 5


def test_frozen_input_contributes_nothing():
    shares = run(samples=2000, number_relative_sigma=0.0).variance_share
    assert "aerosol number" not in shares


# --- Range handling and refusals -------------------------------------------


def test_draws_outside_the_fitted_range_are_discarded_and_reported():
    """Sampling at the edge of a fit must not extrapolate silently."""
    result = run(temperature_c=DUST.t_max_c, temperature_sigma_k=2.0, samples=2000)
    assert result.out_of_range_fraction > 0.2
    assert result.samples_usable < result.samples_requested
    assert any("outside" in n for n in result.notes)


def test_a_mostly_unusable_run_says_so():
    result = run(temperature_c=DUST.t_max_c + 1.0, temperature_sigma_k=1.0, samples=1000)
    assert any("fewer than half" in n for n in result.notes)


def test_assumed_sigma_is_disclosed():
    assert run(param=DUST).sigma_assumed is True
    assert any("documented substitute" in n for n in run(param=DUST).notes)
    assert run(param=KF).sigma_assumed is False


def test_structural_error_caveat_is_always_present():
    assert any("structural error" in n for n in run().notes)


def test_rate_parameterizations_are_refused():
    with pytest.raises(ValueError, match="needs ns"):
        run(param=get_parameterization("kaolinite_murray2011"), temperature_c=-30.0)


def test_too_few_samples_refused():
    with pytest.raises(ValueError, match="at least 100"):
        run(samples=10)


def test_monodisperse_sigma_g_refused():
    with pytest.raises(ValueError, match="geometric_sd"):
        run(geometric_sd=1.0)


# --- The Uncertain primitive ----------------------------------------------


def test_fixed_input_never_varies():
    import random

    spec = Uncertain(5.0, 0.0)
    rng = random.Random(0)
    assert {spec.draw(rng) for _ in range(50)} == {5.0}


def test_relative_lognormal_has_the_requested_coefficient_of_variation():
    import random
    import statistics

    spec = Uncertain(10.0, 0.30)
    rng = random.Random(3)
    draws = [spec.draw(rng) for _ in range(20000)]
    assert statistics.mean(draws) == pytest.approx(10.0, rel=0.02)
    assert statistics.pstdev(draws) / statistics.mean(draws) == pytest.approx(
        0.30, rel=0.05
    )
    assert all(d > 0 for d in draws)


def test_log10_kind_spreads_in_decades():
    import random
    import statistics

    spec = Uncertain(1.0, 0.8, "log10")
    rng = random.Random(4)
    draws = [math.log10(spec.draw(rng)) for _ in range(20000)]
    assert statistics.pstdev(draws) == pytest.approx(0.8, rel=0.05)


# --- CLI -------------------------------------------------------------------


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ina_sim", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_cli_uncertainty_runs():
    proc = _cli(
        "uncertainty",
        "--id",
        "desert_dust_niemand2012",
        "--mode",
        "1.0:0.8:1.9",
        "--temp",
        "-20",
        "--threshold",
        "1.0",
    )
    assert proc.returncode == 0, proc.stderr
    assert "Where the spread comes from" in proc.stdout
    assert "P(n_INP > 1 /L)" in proc.stdout


def test_cli_uncertainty_json_is_reproducible():
    args = (
        "uncertainty",
        "--id",
        "k_feldspar_harrison2019",
        "--mode",
        "1.0:0.8:1.9",
        "--temp",
        "-20",
        "--samples",
        "600",
        "--json",
    )
    first = json.loads(_cli(*args).stdout)
    second = json.loads(_cli(*args).stdout)
    assert first == second
    assert first["variance_share"]
    assert first["n_inp_per_litre"]["p50"] > 0


def test_cli_uncertainty_rejects_a_bad_mode():
    proc = _cli("uncertainty", "--id", "k_feldspar_harrison2019", "--mode", "oops")
    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr

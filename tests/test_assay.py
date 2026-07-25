"""Importing a researcher's own droplet-freezing run.

The headline test is the round trip: simulate droplets freezing under a
published fit, write them out as a CSV, read that CSV back through the public
import path, and require that the recovered ns(T) matches the fit it came from.
That exercises parsing, area resolution, the Vali inversion, the uncertainty
band and the comparison in one go.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from ina_sim.assay import (
    AssayError,
    build_spectrum,
    compare_to_registry,
    load_assay,
    wilson_interval,
)
from ina_sim.units import micrometres_to_metres, sphere_surface_area_m2

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "examples" / "kfeldspar_synthetic_assay.csv"

HEADER = """# area_basis: BET
# concentration_g_per_l: 0.05
# droplet_volume_ul: 1.0
# specific_surface_area_m2_per_g: 3.0
temperature_c,n_frozen,n_total
"""


def write(tmp_path: Path, body: str, header: str = HEADER, name: str = "run.csv") -> Path:
    path = tmp_path / name
    path.write_text(header + body, encoding="utf-8")
    return path


# --- Wilson score interval -------------------------------------------------


def test_wilson_matches_published_values():
    """Standard 95% Wilson intervals, checked against textbook values."""
    lo, hi = wilson_interval(50, 100)
    assert lo == pytest.approx(0.4038, abs=5e-4)
    assert hi == pytest.approx(0.5962, abs=5e-4)


def test_wilson_stays_informative_at_zero_and_one():
    """The reason Wilson is used instead of the normal approximation: the
    interval must not collapse to zero width at the ends of a freezing curve."""
    lo, hi = wilson_interval(0, 100)
    assert lo == 0.0
    assert hi == pytest.approx(0.0370, abs=5e-4)
    lo, hi = wilson_interval(100, 100)
    assert hi == 1.0
    assert lo == pytest.approx(0.9630, abs=5e-4)


@pytest.mark.parametrize("k,n", [(0, 10), (1, 10), (5, 10), (9, 10), (10, 10), (3, 1000)])
def test_wilson_brackets_the_estimate_and_stays_in_range(k, n):
    lo, hi = wilson_interval(k, n)
    assert 0.0 <= lo <= k / n <= hi <= 1.0


def test_wilson_narrows_with_more_droplets():
    small = wilson_interval(50, 100)
    large = wilson_interval(500, 1000)
    assert (large[1] - large[0]) < (small[1] - small[0])


def test_wilson_rejects_impossible_counts():
    with pytest.raises(ValueError):
        wilson_interval(11, 10)
    with pytest.raises(ValueError):
        wilson_interval(1, 0)


# --- Surface area routes ---------------------------------------------------


def test_three_area_routes_agree_when_equivalent(tmp_path):
    """Same physical area expressed three ways must give the same answer."""
    area = 1.5e-7
    body = "-15,50,100\n"

    explicit = load_assay(
        write(
            tmp_path,
            body,
            header=f"# area_basis: BET\n# surface_area_m2_per_droplet: {area}\n"
            "temperature_c,n_frozen,n_total\n",
            name="explicit.csv",
        )
    )
    suspension = load_assay(write(tmp_path, body, name="suspension.csv"))

    diameter_um = 1.0
    per_particle = sphere_surface_area_m2(micrometres_to_metres(diameter_um))
    particles = area / per_particle
    geometric = load_assay(
        write(
            tmp_path,
            body,
            header=(
                "# area_basis: geometric\n"
                f"# particle_diameter_um: {diameter_um}\n"
                f"# particles_per_droplet: {particles}\n"
                "temperature_c,n_frozen,n_total\n"
            ),
            name="particles.csv",
        )
    )

    for assay in (explicit, suspension, geometric):
        assert assay.area_per_droplet_m2()[0] == pytest.approx(area, rel=1e-9)


def test_area_basis_is_required(tmp_path):
    path = write(
        tmp_path,
        "-15,50,100\n",
        header="# surface_area_m2_per_droplet: 1e-7\ntemperature_c,n_frozen,n_total\n",
    )
    with pytest.raises(AssayError, match="area_basis is required"):
        load_assay(path)


def test_incomplete_suspension_recipe_says_what_is_missing(tmp_path):
    path = write(
        tmp_path,
        "-15,50,100\n",
        header="# area_basis: BET\n# concentration_g_per_l: 0.05\n"
        "temperature_c,n_frozen,n_total\n",
    )
    with pytest.raises(AssayError, match="specific_surface_area_m2_per_g"):
        load_assay(path).area_per_droplet_m2()


def test_no_area_information_at_all_is_a_clear_error(tmp_path):
    path = write(
        tmp_path,
        "-15,50,100\n",
        header="# area_basis: BET\ntemperature_c,n_frozen,n_total\n",
    )
    with pytest.raises(AssayError, match="cannot determine droplet surface area"):
        load_assay(path).area_per_droplet_m2()


def test_cli_flags_override_file_metadata(tmp_path):
    path = write(tmp_path, "-15,50,100\n")
    assay = load_assay(path, overrides={"surface_area_m2_per_droplet": 9e-7})
    assert assay.area_per_droplet_m2()[0] == pytest.approx(9e-7)


# --- Parsing ---------------------------------------------------------------


def test_column_aliases_are_accepted(tmp_path):
    path = write(
        tmp_path,
        "-15,50,100\n",
        header="# area_basis: BET\n# surface_area_m2_per_droplet: 1e-7\n"
        "T_c,frozen,droplets\n",
    )
    assay = load_assay(path)
    assert assay.readings[0].n_frozen == 50


def test_differential_counting_accumulates(tmp_path):
    path = write(
        tmp_path,
        "-14,10,100\n-15,20,100\n-16,30,100\n",
        header="# area_basis: BET\n# surface_area_m2_per_droplet: 1e-7\n"
        "# counting: differential\ntemperature_c,n_newly_frozen,n_total\n",
    )
    assay = load_assay(path)
    assert [r.n_frozen for r in assay.readings] == [10, 30, 60]


def test_non_monotonic_cumulative_counts_are_rejected_with_a_hint(tmp_path):
    path = write(tmp_path, "-14,50,100\n-15,20,100\n")
    with pytest.raises(AssayError, match="counting: differential"):
        load_assay(path)


def test_rows_are_sorted_warm_to_cold_regardless_of_file_order(tmp_path):
    path = write(tmp_path, "-16,80,100\n-14,20,100\n-15,50,100\n")
    assay = load_assay(path)
    assert [r.temperature_c for r in assay.readings] == [-14.0, -15.0, -16.0]


def test_frozen_count_above_total_is_rejected(tmp_path):
    with pytest.raises(AssayError, match="outside"):
        load_assay(write(tmp_path, "-15,150,100\n"))


def test_missing_columns_name_what_was_expected(tmp_path):
    path = write(
        tmp_path,
        "-15,50\n",
        header="# area_basis: BET\n# surface_area_m2_per_droplet: 1e-7\n"
        "temperature_c,n_frozen\n",
    )
    with pytest.raises(AssayError, match="droplet total"):
        load_assay(path)


def test_json_input(tmp_path):
    path = tmp_path / "run.json"
    path.write_text(
        json.dumps(
            {
                "metadata": {
                    "area_basis": "geometric",
                    "particle_diameter_um": 1.0,
                    "particles_per_droplet": 1,
                    "material": "test dust",
                },
                "measurements": [
                    {"temperature_c": -20, "n_frozen": 25, "n_total": 100},
                    {"temperature_c": -25, "n_frozen": 75, "n_total": 100},
                ],
            }
        ),
        encoding="utf-8",
    )
    assay = load_assay(path)
    assert assay.metadata.material == "test dust"
    assert len(assay.readings) == 2


def test_unsupported_extension_is_refused(tmp_path):
    path = tmp_path / "run.xlsx"
    path.write_text("nope", encoding="utf-8")
    with pytest.raises(AssayError, match="unsupported extension"):
        load_assay(path)


def test_missing_file_is_refused(tmp_path):
    with pytest.raises(AssayError, match="no such file"):
        load_assay(tmp_path / "absent.csv")


# --- Inversion and its limits ----------------------------------------------


def test_zero_and_full_freezing_become_one_sided_limits(tmp_path):
    spectrum = build_spectrum(load_assay(write(tmp_path, "-10,0,100\n-30,100,100\n")))
    warm, cold = spectrum.points
    assert warm.limit == "upper" and warm.ns_m2 is None and warm.ns_high_m2 > 0
    assert cold.limit == "lower" and cold.ns_m2 is None and cold.ns_low_m2 > 0


def test_central_value_matches_the_vali_inversion(tmp_path):
    spectrum = build_spectrum(load_assay(write(tmp_path, "-15,50,100\n")))
    point = spectrum.points[0]
    expected = -math.log(1 - 0.5) / spectrum.area_m2
    assert point.ns_m2 == pytest.approx(expected, rel=1e-12)


def test_band_brackets_the_central_value(tmp_path):
    spectrum = build_spectrum(load_assay(write(tmp_path, "-15,30,100\n")))
    point = spectrum.points[0]
    assert point.ns_low_m2 < point.ns_m2 < point.ns_high_m2


def test_dynamic_range_is_set_by_droplet_count(tmp_path):
    """With N droplets you cannot resolve below ~1/(N·A) or above ln(N)/A."""
    spectrum = build_spectrum(load_assay(write(tmp_path, "-15,50,100\n")))
    assert spectrum.ns_resolvable_min_m2 == pytest.approx(
        -math.log1p(-1 / 100) / spectrum.area_m2
    )
    assert spectrum.ns_resolvable_max_m2 == pytest.approx(
        math.log(100) / spectrum.area_m2
    )
    assert spectrum.ns_resolvable_max_m2 > spectrum.ns_resolvable_min_m2


def test_more_droplets_widen_the_resolvable_window(tmp_path):
    few = build_spectrum(load_assay(write(tmp_path, "-15,5,10\n", name="few.csv")))
    many = build_spectrum(
        load_assay(write(tmp_path, "-15,500,1000\n", name="many.csv"))
    )
    assert many.ns_resolvable_min_m2 < few.ns_resolvable_min_m2
    assert many.ns_resolvable_max_m2 > few.ns_resolvable_max_m2


def test_tighter_confidence_gives_a_narrower_band(tmp_path):
    assay = load_assay(write(tmp_path, "-15,30,100\n"))
    wide = build_spectrum(assay, confidence=0.99).points[0]
    narrow = build_spectrum(assay, confidence=0.68).points[0]
    assert (narrow.ns_high_m2 - narrow.ns_low_m2) < (wide.ns_high_m2 - wide.ns_low_m2)


def test_measured_t50_is_interpolated(tmp_path):
    spectrum = build_spectrum(load_assay(write(tmp_path, "-14,40,100\n-15,60,100\n")))
    assert spectrum.t50_c() == pytest.approx(-14.5, abs=1e-6)


def test_csv_export_round_trips_through_a_reader(tmp_path):
    spectrum = build_spectrum(load_assay(write(tmp_path, "-14,40,100\n-15,60,100\n")))
    text = spectrum.to_csv()
    lines = text.strip().splitlines()
    assert lines[0].startswith("T_c,")
    assert len(lines) == 3


# --- Comparison against the registry ---------------------------------------


def test_example_file_is_labelled_synthetic():
    head = EXAMPLE.read_text(encoding="utf-8")[:200]
    assert "SYNTHETIC" in head and "NOT A MEASUREMENT" in head


def test_round_trip_recovers_the_fit_it_was_simulated_from():
    """The whole pipeline, end to end: a run simulated under the K-feldspar fit
    must come back consistent with the K-feldspar fit and inconsistent with the
    other minerals."""
    spectrum = build_spectrum(load_assay(EXAMPLE))
    comparisons = {c.parameterization_id: c for c in compare_to_registry(spectrum)}

    kf = comparisons["k_feldspar_harrison2019"]
    assert kf.n_compared >= 10
    assert abs(kf.bias_log10) < 0.3, "recovered ns is offset from its own source"
    assert kf.coverage_fraction > 0.9
    assert kf.verdict == "consistent with this fit"

    for other in ("quartz_harrison2019", "plagioclase_harrison2019"):
        assert comparisons[other].bias_log10 > 1.0


def test_comparison_excludes_other_area_bases():
    """A BET measurement must not be compared against geometric-basis fits."""
    spectrum = build_spectrum(load_assay(EXAMPLE))
    ids = {c.parameterization_id for c in compare_to_registry(spectrum)}
    assert "desert_dust_niemand2012" not in ids
    assert "agi_marcolli2016_derived" not in ids
    assert "k_feldspar_harrison2019" in ids


def test_comparison_excludes_rate_parameterizations():
    spectrum = build_spectrum(load_assay(EXAMPLE))
    ids = {c.parameterization_id for c in compare_to_registry(spectrum)}
    assert "kaolinite_murray2011" not in ids
    assert "water_homogeneous_murray2010" not in ids


def test_comparison_reports_no_overlap_rather_than_guessing(tmp_path):
    """A run entirely outside a fit's range must say so, not extrapolate."""
    path = write(
        tmp_path,
        "-5,50,100\n",
        header="# area_basis: BET\n# surface_area_m2_per_droplet: 1.5e-7\n"
        "temperature_c,n_frozen,n_total\n",
    )
    spectrum = build_spectrum(load_assay(path))
    comparisons = {c.parameterization_id: c for c in compare_to_registry(spectrum)}
    quartz = comparisons["quartz_harrison2019"]  # valid only below -10.5 C
    assert quartz.n_compared == 0
    assert "no overlap" in quartz.verdict


# --- CLI -------------------------------------------------------------------


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ina_sim", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_cli_assay_runs_on_the_example():
    proc = _cli("assay", str(EXAMPLE))
    assert proc.returncode == 0, proc.stderr
    assert "consistent with this fit" in proc.stdout
    assert "Wilson score interval" in proc.stdout


def test_cli_assay_json_is_valid_and_carries_provenance():
    proc = _cli("assay", str(EXAMPLE), "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["source"]["sha256"]
    assert payload["area_basis"] == "BET"
    assert payload["comparisons"][0]["parameterization"] == "k_feldspar_harrison2019"
    assert "uncertainty_note" in payload


def test_cli_assay_reports_a_bad_file_without_a_traceback(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("temperature_c,n_frozen,n_total\n-15,50,100\n", encoding="utf-8")
    proc = _cli("assay", str(bad))
    assert proc.returncode == 1
    assert "area_basis is required" in proc.stderr
    assert "Traceback" not in proc.stderr

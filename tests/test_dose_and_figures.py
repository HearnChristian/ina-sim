"""Size and dose actually move the answer; the figure page renders offline.

Before v0.3.4 the particle-diameter input changed nothing and seeding density
saturated at an arbitrary 50 per litre, so most of the controls were inert.
These tests pin the physics that fixed that, and pin the two things that must
NOT change: the relative score at the reference diameter, and the fact that
pressure and immersion-mode humidity are still (correctly) inert.
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pytest

from ina_sim.library.loader import get_candidate
from ina_sim.models.conditions import Conditions
from ina_sim.physics.dose import (
    REFERENCE_DIAMETER_UM,
    activation,
    effective_ns_from_score,
    slider_sensitivity,
)
from ina_sim.screen.rank import screen_one

REPO_ROOT = Path(__file__).resolve().parents[1]


def act(**kw):
    body = {
        "temperature_c": -10.0,
        "score": 0.5,
        "particle_diameter_um": 1.0,
        "seeding_density_per_l": 100.0,
    }
    body.update(kw)
    return activation(**body)


# --- The reinterpretation is exact at the reference diameter ---------------


@pytest.mark.parametrize("score", [0.001, 0.05, 0.5, 0.909, 0.999])
def test_heuristic_score_is_recovered_exactly_at_one_micron(score):
    """The whole point of the convention: nothing that already worked moves."""
    result = act(score=score, particle_diameter_um=REFERENCE_DIAMETER_UM)
    assert result.activation_probability == pytest.approx(score, rel=1e-9)
    assert result.ns_source == "heuristic_reference"


def test_effective_ns_inverts_the_activation_formula():
    ns = effective_ns_from_score(0.5)
    area = math.pi * 1e-12
    assert 1.0 - math.exp(-ns * area) == pytest.approx(0.5, rel=1e-12)


def test_zero_score_gives_zero_activation():
    assert act(score=0.0).activation_probability == 0.0


def test_score_outside_unit_interval_is_rejected():
    with pytest.raises(ValueError):
        effective_ns_from_score(1.5)


# --- Size now matters, with the right exponent -----------------------------


def test_activation_rises_with_diameter():
    small = act(particle_diameter_um=0.1).activation_probability
    mid = act(particle_diameter_um=1.0).activation_probability
    large = act(particle_diameter_um=5.0).activation_probability
    assert small < mid < large


def test_activation_scales_as_area_in_the_dilute_limit():
    """For ns*A << 1, doubling the diameter must quadruple the probability."""
    a = act(score=1e-4, particle_diameter_um=0.5).activation_probability
    b = act(score=1e-4, particle_diameter_um=1.0).activation_probability
    assert b / a == pytest.approx(4.0, rel=1e-3)


def test_activation_saturates_at_one_for_large_particles():
    assert act(score=0.9, particle_diameter_um=50.0).activation_probability == pytest.approx(
        1.0, abs=1e-9
    )


def test_measured_ns_is_preferred_over_the_convention():
    result = act(measured_ns_m2=1e10)
    assert result.ns_source == "measured"
    assert result.note is None
    assert result.ns_m2 == 1e10


def test_the_convention_is_labelled_when_it_is_used():
    result = act()
    assert result.ns_source == "heuristic_reference"
    assert "convention, not a measurement" in result.note


# --- Dose is linear and uncapped ------------------------------------------


@pytest.mark.parametrize("density", [0.0, 1.0, 50.0, 100.0, 5000.0])
def test_inp_concentration_is_linear_in_dose(density):
    result = act(seeding_density_per_l=density)
    assert result.n_inp_per_litre == pytest.approx(
        density * result.activation_probability, rel=1e-12
    )


def test_dose_does_not_saturate_at_the_old_fifty_per_litre_cap():
    low = act(seeding_density_per_l=50.0).n_inp_per_litre
    high = act(seeding_density_per_l=500.0).n_inp_per_litre
    assert high == pytest.approx(10 * low, rel=1e-12)


def test_negative_inputs_rejected():
    with pytest.raises(ValueError):
        act(seeding_density_per_l=-1.0)
    with pytest.raises(ValueError):
        act(particle_diameter_um=0.0)


# --- End to end through the screen ----------------------------------------


def screen_agi(**kw):
    body = {"temperature_c": -10.0}
    body.update(kw)
    return screen_one(get_candidate("agi"), Conditions(**body))


def test_diameter_now_moves_the_reported_activation():
    small = screen_agi(particle_diameter_um=0.1).details["activation"]
    large = screen_agi(particle_diameter_um=5.0).details["activation"]
    assert large["activation_probability"] > 20 * small["activation_probability"]


def test_density_now_moves_the_reported_inp_concentration():
    few = screen_agi(seeding_density_per_l=10.0).details["activation"]
    many = screen_agi(seeding_density_per_l=1000.0).details["activation"]
    assert many["n_inp_per_litre"] == pytest.approx(100 * few["n_inp_per_litre"], rel=1e-9)


def test_relative_score_is_unchanged_by_particle_size():
    """Size acts on activation and INP concentration, not on the relative
    score, so the demo table cannot move when the diameter slider does."""
    baseline = screen_agi().relative_ina_score
    for diameter in (0.2, 1.0, 8.0):
        assert screen_agi(particle_diameter_um=diameter).relative_ina_score == (
            pytest.approx(baseline)
        )


def test_legacy_loading_factor_saturates_but_cannot_reorder():
    """The score's min(1, N/50) loading factor has no physical basis. It is kept
    because zero dose giving zero score is a tested property, and it is safe
    because it scales every candidate identically."""
    from ina_sim.library.loader import load_candidates
    from ina_sim.screen.rank import rank_candidates

    assert screen_agi(seeding_density_per_l=100.0).relative_ina_score == pytest.approx(
        screen_agi(seeding_density_per_l=900.0).relative_ina_score
    )
    assert screen_agi(seeding_density_per_l=10.0).relative_ina_score < screen_agi(
        seeding_density_per_l=100.0
    ).relative_ina_score

    cands = list(load_candidates(include_uploads=False))
    order_low = [
        r.candidate.id
        for r in rank_candidates(
            cands, Conditions(temperature_c=-10.0, seeding_density_per_l=5.0)
        )
    ]
    order_high = [
        r.candidate.id
        for r in rank_candidates(
            cands, Conditions(temperature_c=-10.0, seeding_density_per_l=500.0)
        )
    ]
    assert order_low == order_high


def test_pressure_and_immersion_humidity_remain_inert_on_purpose():
    """These two are honestly inert - immersion freezing does not care. If this
    test ever fails, someone has added fake sensitivity."""
    baseline = screen_agi().overall_efficiency
    assert screen_agi(pressure_hpa=500.0).overall_efficiency == pytest.approx(baseline)
    assert screen_agi(relative_humidity_pct=70.0).overall_efficiency == pytest.approx(
        baseline
    )


def test_slider_sensitivity_documents_every_condition_field():
    documented = set(slider_sensitivity())
    fields = set(Conditions().as_dict())
    undocumented = fields - documented - {"mode", "track"}
    assert not undocumented, f"inputs with no stated effect: {sorted(undocumented)}"


# --- Reference figures -----------------------------------------------------


def test_every_figure_builds_and_carries_a_caption():
    from ina_sim.figures import build_figures

    figures = build_figures()
    assert len(figures) >= 8
    for fig in figures:
        assert fig["svg"].startswith("<svg")
        assert fig["svg"].rstrip().endswith("</svg>")
        assert len(fig["caption"]) > 80, fig["title"]


def test_figures_contain_no_nan_coordinates():
    """A NaN in a path silently breaks the whole polyline in some renderers."""
    from ina_sim.figures import build_figures

    for fig in build_figures():
        assert "nan" not in fig["svg"].lower()


def test_page_is_self_contained_and_offline():
    from ina_sim.figures import build_figures, render_page

    html = render_page(build_figures())
    # The SVG xmlns is a namespace identifier, never fetched, so it is stripped
    # before checking that nothing else reaches the network.
    stripped = html.replace('xmlns="http://www.w3.org/2000/svg"', "")
    for forbidden in ("http://", "https://", "<script", "@import", "src=", "url("):
        assert forbidden not in stripped, f"page is not self-contained: {forbidden!r}"
    assert html.startswith("<!doctype html>")


def test_page_states_what_each_input_does():
    from ina_sim.figures import build_figures, render_page

    html = render_page(build_figures())
    assert "particle_diameter_um" in html
    assert "seeding_density_per_l" in html
    assert "Overseeding" in html


def test_cli_figures_writes_a_file(tmp_path):
    out = tmp_path / "figs.html"
    proc = subprocess.run(
        [sys.executable, "-m", "ina_sim", "figures", "--out", str(out)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert out.is_file()
    assert out.read_text(encoding="utf-8").count("<svg") >= 8

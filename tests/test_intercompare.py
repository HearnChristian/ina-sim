"""Intercomparison must not confuse 'different materials' with 'disagreement'.

The whole value of this view is that it separates two things that look alike in
a plot: fits that differ because the substances differ, and fits that differ
because the measurements conflict. Only the second is a problem, and only the
second is flagged.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ina_sim.physics.intercompare import (
    comparison_key,
    intercompare,
    summarise,
    temperature_grid,
)
from ina_sim.physics.ns import Parameterization, load_parameterizations

REPO_ROOT = Path(__file__).resolve().parents[1]
GRID = temperature_grid(-35.0, -10.0, 5.0)


def test_temperature_grid_runs_warm_to_cold():
    assert GRID[0] == -10.0
    assert GRID[-1] == -35.0
    assert len(GRID) == 6


def test_temperature_grid_rejects_a_bad_step():
    with pytest.raises(ValueError):
        temperature_grid(-30.0, -10.0, 0.0)


def test_groups_never_mix_quantities_or_area_bases():
    for group in intercompare(temperatures=GRID):
        params = [load_parameterizations()[pid] for pid in group.parameterization_ids]
        assert len({p.quantity for p in params}) == 1
        assert len({p.area_basis for p in params}) == 1
        assert all(comparison_key(p) == comparison_key(params[0]) for p in params)


def test_bet_and_geometric_fits_land_in_different_groups():
    groups = intercompare(temperatures=GRID)
    membership = {
        pid: (g.quantity, g.area_basis) for g in groups for pid in g.parameterization_ids
    }
    assert membership["k_feldspar_harrison2019"] != membership["desert_dust_niemand2012"]
    assert membership["kaolinite_murray2011"] != membership["k_feldspar_harrison2019"]


def test_no_conflict_is_reported_between_different_materials():
    """Feldspar and plagioclase differ by decades; that is mineralogy, not a
    contradiction in the literature."""
    for group in intercompare(temperatures=GRID):
        if group.disagreement_testable:
            continue
        assert group.n_conflicts == 0, (
            f"{group.area_basis} group flagged a conflict between different materials"
        )


def test_spread_is_still_reported_for_different_materials():
    bet = next(
        g
        for g in intercompare(temperatures=GRID)
        if g.area_basis == "BET" and len(g.parameterization_ids) > 1
    )
    assert bet.max_spread_log10 > 1.0
    assert bet.same_material_pairs == 0
    assert bet.disagreement_testable is False


def test_same_material_disagreement_is_detected():
    """Inject a second fit for an existing material that is deliberately wrong,
    and the conflict must be found."""
    registry = dict(load_parameterizations())
    real = registry["k_feldspar_harrison2019"]
    impostor = Parameterization(
        id="k_feldspar_impostor",
        material="K-feldspar (fabricated for this test)",
        material_key=real.material_key,
        status="derived",
        kind="singular",
        mode="immersion",
        form="log10_linear_c",
        # Three decades below the real fit across the whole range.
        coefficients=(real.coefficients[0] - 3.0 + 4.0, -0.3),
        units="m^-2",
        area_basis=real.area_basis,
        t_min_c=real.t_min_c,
        t_max_c=real.t_max_c,
        reference=real.reference,
        sigma_log10=0.2,
    )
    registry["k_feldspar_impostor"] = impostor

    groups = intercompare(
        temperatures=GRID,
        ids=["k_feldspar_harrison2019", "k_feldspar_impostor"],
        parameterizations=registry,
    )
    group = groups[0]
    assert group.same_material_pairs == 1
    assert group.disagreement_testable is True
    assert group.n_conflicts > 0
    conflicted = next(r for r in group.rows if r.conflict)
    a, b, gap, sigma = conflicted.conflicts[0]
    assert {a, b} == {"k_feldspar_harrison2019", "k_feldspar_impostor"}
    assert gap > sigma


def test_agreeing_fits_of_the_same_material_are_not_flagged():
    registry = dict(load_parameterizations())
    real = registry["k_feldspar_harrison2019"]
    twin = Parameterization(
        id="k_feldspar_twin",
        material="K-feldspar (near duplicate)",
        material_key=real.material_key,
        status="published",
        kind="singular",
        mode="immersion",
        form=real.form,
        coefficients=(real.coefficients[0] + 0.1,) + real.coefficients[1:],
        units=real.units,
        area_basis=real.area_basis,
        t_min_c=real.t_min_c,
        t_max_c=real.t_max_c,
        reference=real.reference,
        sigma_log10=0.8,
    )
    registry["k_feldspar_twin"] = twin
    group = intercompare(
        temperatures=GRID,
        ids=["k_feldspar_harrison2019", "k_feldspar_twin"],
        parameterizations=registry,
    )[0]
    assert group.disagreement_testable is True
    assert group.n_conflicts == 0


def test_out_of_range_cells_are_empty_not_extrapolated():
    group = next(
        g for g in intercompare(temperatures=GRID) if g.area_basis == "BET"
    )
    row = next(r for r in group.rows if r.temperature_c == -10.0)
    quartz = next(
        c for c in row.cells if c.parameterization_id == "quartz_harrison2019"
    )
    assert quartz.log10_value is None  # quartz fit starts at -10.5 C
    assert quartz.in_range is False


def test_single_member_groups_report_no_spread():
    groups = intercompare(temperatures=GRID)
    for group in groups:
        if len(group.parameterization_ids) == 1:
            assert all(r.spread_log10 is None for r in group.rows)


def test_filtering_by_id_and_basis():
    groups = intercompare(temperatures=GRID, area_basis="BET")
    assert all(g.area_basis == "BET" for g in groups)
    picked = intercompare(
        temperatures=GRID, ids=["k_feldspar_harrison2019", "quartz_harrison2019"]
    )
    assert sum(len(g.parameterization_ids) for g in picked) == 2


def test_unknown_id_is_an_error():
    with pytest.raises(KeyError, match="unknown parameterization"):
        intercompare(temperatures=GRID, ids=["not_a_fit"])


def test_summary_counts_the_registry_honestly():
    summary = summarise(intercompare(temperatures=GRID))
    assert summary["n_groups"] >= 3
    assert summary["n_groups_with_same_material_pairs"] == 0
    assert "adding a second fit" in summary["note"]


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ina_sim", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_cli_compare_runs_and_explains_itself():
    proc = _cli("compare", "--range=-35:-10:5")
    assert proc.returncode == 0, proc.stderr
    assert "NOT a disagreement between fits" in proc.stdout
    assert "CONFLICT" not in proc.stdout.split("values are log10")[0]


def test_cli_compare_json():
    proc = _cli("compare", "--temp", "-20", "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["summary"]["n_groups"] >= 3
    for group in payload["groups"]:
        for row in group["rows"]:
            assert row["spread_meaning"].startswith("range across different materials")


def test_cli_compare_rejects_a_bad_range():
    proc = _cli("compare", "--range=nonsense")
    assert proc.returncode == 1
    assert "lo:hi:step" in proc.stderr


# --- Empirical-only ranking ------------------------------------------------


def test_ranking_covers_every_measured_material_not_just_library_ones():
    """The gap this closes: quartz, plagioclase, albite and desert dust have
    published fits but no library candidate, so the heuristic screen never sees
    them. The empirical ranking does."""
    from ina_sim.physics.intercompare import empirical_ranking

    ranked = {
        r.material_key
        for rows in empirical_ranking(-20.0).values()
        for r in rows
    }
    assert {"quartz", "plagioclase", "albite", "desert_dust"} <= ranked
    assert "k_feldspar" in ranked


def test_ranking_is_sorted_and_grouped_by_comparability():
    from ina_sim.physics.intercompare import empirical_ranking

    for (quantity, basis), rows in empirical_ranking(-20.0).items():
        assert [r.log10_value for r in rows] == sorted(
            (r.log10_value for r in rows), reverse=True
        )
        assert all(r.units == rows[0].units for r in rows)
        assert rows[0].decades_below_top == 0.0
        assert all(r.decades_below_top >= 0 for r in rows)


def test_ranking_reproduces_the_published_mineral_order():
    """Harrison et al. (2019): K-feldspar most active, plagioclase least."""
    from ina_sim.physics.intercompare import empirical_ranking

    bet = empirical_ranking(-20.0, area_basis="BET")[("ns", "BET")]
    assert [r.material_key for r in bet] == [
        "k_feldspar",
        "albite",
        "quartz",
        "plagioclase",
    ]


def test_ranking_never_mixes_bases():
    from ina_sim.physics.intercompare import empirical_ranking

    groups = empirical_ranking(-20.0)
    keys = {(q, b) for q, b in groups}
    assert ("ns", "BET") in keys and ("ns", "geometric") in keys
    bet_materials = {r.material_key for r in groups[("ns", "BET")]}
    assert "desert_dust" not in bet_materials
    assert "agi" not in bet_materials


def test_ranking_excludes_materials_outside_their_fitted_range():
    from ina_sim.physics.intercompare import empirical_ranking

    warm = empirical_ranking(-5.0)
    materials = {r.material_key for rows in warm.values() for r in rows}
    assert "quartz" not in materials  # quartz fit starts at -10.5 C
    assert "k_feldspar" in materials  # valid from -3.5 C


def test_ranking_marks_assumed_uncertainty_and_derived_status():
    from ina_sim.physics.intercompare import empirical_ranking

    geometric = empirical_ranking(-20.0, area_basis="geometric")[("ns", "geometric")]
    by_key = {r.material_key: r for r in geometric}
    assert by_key["desert_dust"].sigma_assumed is True
    assert by_key["agi"].status == "derived"


def test_cli_rank_runs():
    proc = _cli("rank", "--temp", "-20")
    assert proc.returncode == 0, proc.stderr
    assert "k_feldspar" in proc.stdout
    assert "quartz" in proc.stdout
    assert "heuristic layer off" in proc.stdout


def test_cli_rank_json_groups():
    proc = _cli("rank", "--temp", "-20", "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    bases = {g["area_basis"] for g in payload["groups"]}
    assert {"BET", "geometric"} <= bases


def test_cli_rank_reports_nothing_measured_plainly():
    proc = _cli("rank", "--temp", "-1")
    assert proc.returncode == 0
    assert "No parameterization covers" in proc.stdout

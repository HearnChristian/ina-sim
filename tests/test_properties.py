"""Property-style invariants for physics + ranking."""

from __future__ import annotations

import math

from ina_sim.library.loader import filter_candidates, load_candidates
from ina_sim.models.conditions import Conditions
from ina_sim.physics.atmosphere import total_water_vapor_kg
from ina_sim.screen.rank import rank_candidates, screen_one


def test_efficiency_and_relina_bounded():
    for c in load_candidates():
        r = screen_one(c, Conditions(temperature_c=-10.0))
        assert 0.0 <= r.overall_efficiency <= 1.0
        assert r.relative_ina_score >= 0.0
        assert r.relative_ina_low <= r.relative_ina_score <= r.relative_ina_high
        assert math.isfinite(r.relative_ina_score)


def test_vapor_mass_nonnegative_grid():
    for t in (-30, -10, 0, 10):
        for rh in (0, 50, 100):
            m = total_water_vapor_kg(1e6, float(t), float(rh), 850.0)
            assert m >= 0.0 and math.isfinite(m)


def test_zero_density_zero_efficiency():
    cands = filter_candidates(tags=["starter-set"])
    ranked = rank_candidates(
        cands, Conditions(temperature_c=-10.0, seeding_density_per_l=0.0)
    )
    for r in ranked:
        assert r.overall_efficiency == 0.0


def test_controls_below_agi_mixed_phase():
    ranked = rank_candidates(
        list(load_candidates()), Conditions(temperature_c=-10.0, track="ice")
    )
    ids = [r.candidate.id for r in ranked]
    assert ids.index("agi") < ids.index("water_control")


def test_warm_cloud_promotes_hygroscopic_over_agi():
    ranked = rank_candidates(
        list(load_candidates()),
        Conditions(temperature_c=0.0, relative_humidity_pct=95.0, track="warm_cloud"),
    )
    ids = [r.candidate.id for r in ranked]
    # NaCl or CaCl2 should beat AgI on warm track
    top_hygro = min(
        (ids.index(i) for i in ("nacl", "cacl2") if i in ids),
        default=999,
    )
    assert top_hygro < ids.index("agi")


def test_identical_conditions_identical_ranking():
    cands = filter_candidates(tags=["starter-set"])
    cond = Conditions(temperature_c=-12.0, track="ice")
    a = [r.candidate.id for r in rank_candidates(cands, cond)]
    b = [r.candidate.id for r in rank_candidates(cands, cond)]
    assert a == b

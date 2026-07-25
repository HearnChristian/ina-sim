"""The empirical registry must stay internally consistent and honest.

These tests encode the rules the registry claims to follow, so a future edit
that quietly breaks one of them fails here rather than in a demo.
"""

from __future__ import annotations

import math

import pytest

from ina_sim.physics.ns import (
    AreaBasisError,
    assert_comparable,
    evaluate,
    evaluate_for_candidate,
    get_parameterization,
    load_parameterizations,
    parameterizations_for,
    registry_summary,
)
from ina_sim.references import load_references

ALL = load_parameterizations()
SINGULAR = [p for p in ALL.values() if p.quantity == "ns"]


def test_registry_is_not_empty():
    assert len(ALL) >= 8


@pytest.mark.parametrize("param", list(ALL.values()), ids=lambda p: p.id)
def test_every_parameterization_cites_a_known_reference(param):
    assert param.reference in load_references()


@pytest.mark.parametrize("param", list(ALL.values()), ids=lambda p: p.id)
def test_validity_range_is_ordered_and_subzero(param):
    assert param.t_min_c < param.t_max_c
    # Every ice nucleation parameterization here is for supercooled conditions.
    assert param.t_max_c < 0.0


@pytest.mark.parametrize("param", list(ALL.values()), ids=lambda p: p.id)
def test_units_match_quantity(param):
    if param.quantity == "ns":
        assert param.units in {"m^-2", "cm^-2"}
        assert param.area_basis in {"BET", "geometric"}
    elif param.quantity == "j_het":
        assert param.units == "cm^-2 s^-1"
    else:
        assert param.units == "cm^-3 s^-1"
        assert param.area_basis == "volume"


@pytest.mark.parametrize("param", list(ALL.values()), ids=lambda p: p.id)
def test_derived_entries_declare_their_derivation(param):
    if param.status == "derived":
        assert param.derivation, "a derived fit must name the script that made it"
        assert param.dataset, "a derived fit must name its dataset"
        assert param.caveat, "a derived fit must state what it is not"


@pytest.mark.parametrize("param", list(ALL.values()), ids=lambda p: p.id)
def test_published_entries_quote_the_source_equation(param):
    if param.status == "published":
        assert param.quote, "a published fit must carry the source's own wording"


@pytest.mark.parametrize("param", ALL.values(), ids=lambda p: p.id)
def test_activity_increases_as_temperature_drops(param):
    """Ice nucleation gets easier as it gets colder, without exception."""
    steps = 25
    span = param.t_max_c - param.t_min_c
    previous = None
    for i in range(steps + 1):
        temp = param.t_max_c - span * i / steps
        est = evaluate(param, temp)
        assert est.value is not None
        assert math.isfinite(est.value)
        if previous is not None:
            assert est.value > previous, (
                f"{param.id} is not monotonic at {temp} C"
            )
        previous = est.value


@pytest.mark.parametrize("param", list(ALL.values()), ids=lambda p: p.id)
def test_refuses_to_extrapolate_by_default(param):
    below = evaluate(param, param.t_min_c - 5.0)
    above = evaluate(param, param.t_max_c + 5.0)
    assert below.value is None and not below.in_range
    assert above.value is None and not above.in_range
    assert any("outside the fitted range" in n for n in below.notes)


@pytest.mark.parametrize("param", list(ALL.values()), ids=lambda p: p.id)
def test_extrapolation_is_flagged_when_requested(param):
    est = evaluate(param, param.t_max_c + 2.0, allow_extrapolation=True)
    assert est.extrapolated is True
    assert est.value is not None
    assert any("EXTRAPOLATED" in n for n in est.notes)


@pytest.mark.parametrize("param", list(ALL.values()), ids=lambda p: p.id)
def test_missing_sigma_is_substituted_and_flagged(param):
    est = evaluate(param, 0.5 * (param.t_min_c + param.t_max_c))
    assert est.sigma_log10 is not None and est.sigma_log10 > 0
    if param.sigma_log10 is None:
        assert est.sigma_assumed is True
        assert any("no uncertainty" in n for n in est.notes)
    else:
        assert est.sigma_assumed is False


@pytest.mark.parametrize("param", SINGULAR, ids=lambda p: p.id)
def test_uncertainty_band_brackets_the_central_value(param):
    est = evaluate(param, 0.5 * (param.t_min_c + param.t_max_c))
    assert est.low < est.value < est.high
    # A band of sigma decades means exactly a factor 10^sigma each way.
    assert est.high / est.value == pytest.approx(10.0**est.sigma_log10, rel=1e-9)


def test_k_feldspar_reproduces_hand_evaluated_polynomial():
    """Independent hand evaluation of the Harrison et al. (2019) fit at -20 C.

    log10(ns) = -3.25 + 15.86 - 27.64 + 33.36 - 16.80 + 2.9056 = 4.4356 (cm^-2)
    """
    est = evaluate(get_parameterization("k_feldspar_harrison2019"), -20.0)
    assert math.log10(est.value) == pytest.approx(4.4356 + 4.0, abs=1e-3)


def test_area_basis_guard_blocks_incomparable_values():
    bet = evaluate(get_parameterization("k_feldspar_harrison2019"), -20.0)
    geometric = evaluate(get_parameterization("desert_dust_niemand2012"), -20.0)
    with pytest.raises(AreaBasisError):
        assert_comparable([bet, geometric])


def test_area_basis_guard_allows_same_basis():
    a = evaluate(get_parameterization("k_feldspar_harrison2019"), -20.0)
    b = evaluate(get_parameterization("quartz_harrison2019"), -20.0)
    assert_comparable([a, b])  # both BET, both ns


def test_quantities_are_never_mixed():
    ns = evaluate(get_parameterization("k_feldspar_harrison2019"), -30.0)
    rate = evaluate(get_parameterization("kaolinite_murray2011"), -30.0)
    with pytest.raises(AreaBasisError):
        assert_comparable([ns, rate])


def test_candidate_lookup_returns_none_for_unmeasured_material():
    assert evaluate_for_candidate("inert_surface", -20.0) is None
    assert parameterizations_for("inert_surface") == []


def test_candidate_lookup_finds_measured_material():
    est = evaluate_for_candidate("k_feldspar", -20.0)
    assert est is not None and est.value is not None
    assert est.parameterization_id == "k_feldspar_harrison2019"


def test_registry_summary_counts_match_the_file():
    summary = registry_summary()
    assert summary["count"] == len(ALL)
    assert summary["published"] + summary["derived"] == summary["count"]

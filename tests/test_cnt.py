from ina_sim.physics.cnt import (
    cnt_activity_score,
    cnt_estimate,
    heterogeneous_factor,
    homogeneous_barrier,
)


def test_heterogeneous_factor_perfect_match_near_zero():
    f = heterogeneous_factor(0.99)
    assert f < 0.05


def test_heterogeneous_factor_no_match_near_one():
    f = heterogeneous_factor(-1.0)
    assert abs(f - 1.0) < 1e-9


def test_homogeneous_barrier_undefined_at_saturation():
    dg, dg_kt, r = homogeneous_barrier(-10.0, 1.0)
    assert dg is None and dg_kt is None and r is None


def test_homogeneous_barrier_finite_when_supersaturated():
    dg, dg_kt, r = homogeneous_barrier(-20.0, 1.2)
    assert dg is not None and dg > 0
    assert dg_kt is not None and dg_kt > 0
    assert r is not None and r > 0


def test_cnt_estimate_deposition_path():
    est = cnt_estimate(-15.0, 1.25, lattice_match=0.9)
    assert est.valid
    assert est.f_hetero < 0.2
    assert est.delta_g_hetero_kt is not None
    assert est.delta_g_hetero_kt < est.delta_g_star_kt


def test_cnt_activity_immersion_proxy_increases_when_colder():
    warm = cnt_activity_score(-5.0, 1.0, 0.9)
    cold = cnt_activity_score(-25.0, 1.0, 0.9)
    assert cold > warm

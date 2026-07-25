"""The audit trail must be tamper-evident, and the scenario must compose honestly.

The audit tests are mostly about detection: an edited or removed record has to be
caught, because a log that cannot detect its own corruption is worse than no log
(it looks like evidence).
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from ina_sim.audit import (
    GENESIS,
    append_run,
    diff_runs,
    read_records,
    record_hash,
    registry_fingerprint,
    summarise,
    verify_chain,
)
from ina_sim.physics.aerosol import LognormalMode
from ina_sim.physics.ns import get_parameterization
from ina_sim.scenario import Payload, run_scenario, solve_payload

REPO_ROOT = Path(__file__).resolve().parents[1]
AGI = get_parameterization("agi_marcolli2016_derived")
KF = get_parameterization("k_feldspar_harrison2019")


def log(tmp_path: Path, n: int = 3) -> Path:
    target = tmp_path / "log.jsonl"
    for i in range(n):
        append_run(
            "scenario",
            inputs={"T_c": -12.0 - i, "payload_kg": 1.0},
            outputs={"n_inp_p50": 10.0 * (i + 1)},
            validation_ok=True,
            path=target,
        )
    return target


# --- Audit chain -----------------------------------------------------------


def test_records_are_appended_in_order_and_chained(tmp_path):
    records = read_records(log(tmp_path))
    assert [r.index for r in records] == [0, 1, 2]
    assert records[0].prev_hash == GENESIS
    assert records[1].prev_hash == records[0].record_hash
    assert records[2].prev_hash == records[1].record_hash
    assert not verify_chain(records)


def test_every_record_carries_the_registry_fingerprint(tmp_path):
    for record in read_records(log(tmp_path, 2)):
        assert record.registry_fingerprint == registry_fingerprint()
        assert record.version


def test_editing_a_record_is_detected(tmp_path):
    target = log(tmp_path)
    lines = target.read_text(encoding="utf-8").splitlines()
    body = json.loads(lines[1])
    body["outputs"]["n_inp_p50"] = 999.0  # quietly change a result
    lines[1] = json.dumps(body, sort_keys=True, separators=(",", ":"))
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")

    problems = verify_chain(read_records(target))
    assert problems
    kinds = {p.kind for p in problems}
    assert "bad_hash" in kinds
    assert any("edited after it was written" in p.detail for p in problems)


def test_removing_a_record_is_detected(tmp_path):
    target = log(tmp_path)
    lines = target.read_text(encoding="utf-8").splitlines()
    target.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")

    problems = verify_chain(read_records(target))
    assert {p.kind for p in problems} >= {"bad_index", "broken_link"}


def test_reordering_records_is_detected(tmp_path):
    target = log(tmp_path)
    lines = target.read_text(encoding="utf-8").splitlines()
    target.write_text("\n".join([lines[0], lines[2], lines[1]]) + "\n", encoding="utf-8")
    assert verify_chain(read_records(target))


def test_hash_covers_the_contents_not_just_the_link():
    body = {"index": 0, "inputs": {"a": 1}, "prev_hash": GENESIS}
    first = record_hash(body)
    body["inputs"]["a"] = 2
    assert record_hash(body) != first


def test_missing_log_is_not_an_error(tmp_path):
    assert read_records(tmp_path / "absent.jsonl") == []


def test_logging_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("INA_SIM_NO_RUN_LOG", "1")
    assert append_run("scenario", inputs={}, outputs={}, path=tmp_path / "l.jsonl") is None
    assert not (tmp_path / "l.jsonl").exists()


def test_summary_counts_registry_versions(tmp_path):
    summary = summarise(read_records(log(tmp_path)))
    assert summary["n_runs"] == 3
    assert summary["distinct_registry_versions"] == 1
    assert summary["runs_on_current_registry"] == 3


# --- Diffs attribute the change --------------------------------------------


def test_diff_blames_the_conditions_when_only_inputs_moved(tmp_path):
    records = read_records(log(tmp_path))
    report = diff_runs(records[0], records[1])
    assert report["verdict"] == "the conditions changed"
    assert report["registry_changed"] is False
    assert "T_c" in report["changed"]["inputs"]
    assert "n_inp_p50" in report["changed"]["outputs"]


def test_diff_blames_the_science_when_the_registry_moved(tmp_path):
    target = tmp_path / "log.jsonl"
    append_run("scenario", inputs={"T_c": -12.0}, outputs={"x": 1.0}, path=target)
    append_run("scenario", inputs={"T_c": -12.0}, outputs={"x": 5.0}, path=target)
    records = read_records(target)
    doctored = type(records[1])(
        **{**records[1].__dict__, "registry_fingerprint": "different_fingerprint"}
    )
    report = diff_runs(records[0], doctored)
    assert report["registry_changed"] is True
    assert "the science changed" in report["verdict"]


def test_diff_notices_identical_outputs(tmp_path):
    target = tmp_path / "log.jsonl"
    append_run("scenario", inputs={"T_c": -12.0}, outputs={"x": 1.0}, path=target)
    append_run("scenario", inputs={"T_c": -18.0}, outputs={"x": 1.0}, path=target)
    records = read_records(target)
    assert diff_runs(records[0], records[1])["verdict"] == "outputs identical"


# --- Scenario physics ------------------------------------------------------


def test_payload_converts_to_particles_by_mass():
    """N = mass / (density x mean particle volume), with the Hatch-Choate third
    moment for the volume."""
    payload = Payload(
        mass_kg=1.0, density_g_cm3=5.67, mode=LognormalMode(1.0, 0.1, 1.8)
    )
    ln_sd = math.log(1.8)
    expected_volume = (math.pi / 6.0) * (0.1e-6) ** 3 * math.exp(4.5 * ln_sd**2)
    assert payload.mean_particle_volume_m3 == pytest.approx(expected_volume, rel=1e-12)
    assert payload.particle_count == pytest.approx(
        1.0 / (expected_volume * 5.67 * 1000.0), rel=1e-12
    )


def test_more_payload_delivers_more():
    small = run_scenario(AGI, payload_kg=0.5, density_g_cm3=5.67,
                         median_diameter_um=0.1, samples=800)
    large = run_scenario(AGI, payload_kg=5.0, density_g_cm3=5.67,
                         median_diameter_um=0.1, samples=800)
    assert large.number_per_cm3 == pytest.approx(10 * small.number_per_cm3, rel=1e-9)
    assert large.monte_carlo.median > small.monte_carlo.median


def test_smaller_particles_give_more_particles_but_less_area_each():
    coarse = Payload(1.0, 5.67, LognormalMode(1.0, 1.0, 1.8)).particle_count
    fine = Payload(1.0, 5.67, LognormalMode(1.0, 0.1, 1.8)).particle_count
    assert fine == pytest.approx(1000 * coarse, rel=1e-9)  # volume scales as d^3


def test_bigger_cloud_dilutes():
    small = run_scenario(AGI, payload_kg=1.0, density_g_cm3=5.67,
                         median_diameter_um=0.1, cloud_volume_m3=1e8, samples=800)
    big = run_scenario(AGI, payload_kg=1.0, density_g_cm3=5.67,
                       median_diameter_um=0.1, cloud_volume_m3=1e10, samples=800)
    assert big.number_per_cm3 == pytest.approx(small.number_per_cm3 / 100, rel=1e-9)


def test_impossible_payloads_rejected():
    with pytest.raises(ValueError):
        Payload(0.0, 5.67, LognormalMode(1.0, 0.1, 1.8))
    with pytest.raises(ValueError):
        Payload(1.0, -1.0, LognormalMode(1.0, 0.1, 1.8))


def test_cost_is_only_reported_when_supplied():
    result = run_scenario(AGI, payload_kg=2.0, density_g_cm3=5.67,
                          median_diameter_um=0.1, samples=500)
    assert result.total_cost is None
    priced = run_scenario(AGI, payload_kg=2.0, density_g_cm3=5.67,
                          median_diameter_um=0.1, cost_per_kg=300.0, samples=500)
    assert priced.total_cost == pytest.approx(600.0)


def test_uniform_mixing_caveat_is_always_first():
    result = run_scenario(AGI, payload_kg=1.0, density_g_cm3=5.67,
                          median_diameter_um=0.1, samples=500)
    assert "upper bound" in result.warnings[0]
    assert "uniformly" in result.warnings[0]


# --- The claims guardrail --------------------------------------------------


def test_claims_refuse_precipitation_and_efficacy():
    result = run_scenario(AGI, payload_kg=1.0, density_g_cm3=5.67,
                          median_diameter_um=0.1, samples=500)
    refused = " ".join(result.claims["refused"]).lower()
    assert "precipitation" in refused
    assert "efficacy" in refused or "dosage" in refused
    assert "caused" in refused


def test_derived_parameterization_is_disclosed_in_the_claims():
    result = run_scenario(AGI, payload_kg=1.0, density_g_cm3=5.67,
                          median_diameter_um=0.1, samples=500)
    conditional = " ".join(result.claims["conditional"])
    assert "derived in this repository" in conditional


# --- Inverse solve ---------------------------------------------------------


def test_solving_for_payload_hits_the_target():
    result = solve_payload(
        AGI,
        target_probability=0.9,
        density_g_cm3=5.67,
        median_diameter_um=0.1,
        temperature_c=-12.0,
        threshold_per_litre=1.0,
        samples=600,
    )
    assert result is not None
    assert result.solved_for_payload is True
    assert result.probability_above_threshold == pytest.approx(0.9, abs=0.06)


def test_a_higher_target_needs_more_payload():
    common = dict(
        density_g_cm3=5.67,
        median_diameter_um=0.1,
        temperature_c=-12.0,
        threshold_per_litre=1.0,
        samples=400,
    )
    modest = solve_payload(AGI, target_probability=0.5, **common)
    strict = solve_payload(AGI, target_probability=0.95, **common)
    assert strict.payload_kg > modest.payload_kg


def test_unreachable_target_returns_none_rather_than_a_huge_number():
    """Too warm for the agent is a real answer, and more useful than 10^6 kg."""
    result = solve_payload(
        KF,
        target_probability=0.99,
        density_g_cm3=2.56,
        median_diameter_um=0.1,
        temperature_c=-4.0,
        threshold_per_litre=1000.0,
        samples=300,
    )
    assert result is None


def test_target_probability_must_be_a_probability():
    with pytest.raises(ValueError):
        solve_payload(AGI, target_probability=1.5, density_g_cm3=5.67,
                      median_diameter_um=0.1)


# --- CLI -------------------------------------------------------------------


def _cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ina_sim", *args],
        capture_output=True,
        text=True,
        cwd=cwd or REPO_ROOT,
    )


def test_cli_scenario_and_history_round_trip(tmp_path):
    proc = _cli(
        "scenario", "--id", "agi_marcolli2016_derived", "--payload-kg", "1.0",
        "--diameter", "0.1", "--temp", "-12", "--samples", "500",
        cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    assert "P(delivered >" in proc.stdout
    assert "It does NOT support:" in proc.stdout

    history = _cli("history", cwd=tmp_path)
    assert history.returncode == 0, history.stderr
    assert "scenario" in history.stdout

    verify = _cli("history", "--verify", cwd=tmp_path)
    assert verify.returncode == 0
    assert "Chain intact" in verify.stdout


def test_cli_scenario_requires_exactly_one_mode(tmp_path):
    both = _cli(
        "scenario", "--id", "agi_marcolli2016_derived", "--payload-kg", "1",
        "--target-probability", "0.9", cwd=tmp_path,
    )
    assert both.returncode == 1
    assert "exactly one" in both.stderr

    neither = _cli("scenario", "--id", "agi_marcolli2016_derived", cwd=tmp_path)
    assert neither.returncode == 1


def test_cli_scenario_needs_a_density_it_cannot_guess(tmp_path):
    proc = _cli(
        "scenario", "--id", "quartz_harrison2019", "--payload-kg", "1",
        "--diameter", "0.5", cwd=tmp_path,
    )
    assert proc.returncode == 1
    assert "--density" in proc.stderr


def test_cli_history_detects_tampering(tmp_path):
    _cli("scenario", "--id", "agi_marcolli2016_derived", "--payload-kg", "1.0",
         "--diameter", "0.1", "--samples", "300", cwd=tmp_path)
    _cli("scenario", "--id", "agi_marcolli2016_derived", "--payload-kg", "2.0",
         "--diameter", "0.1", "--samples", "300", cwd=tmp_path)

    target = tmp_path / "data" / "runs" / "log.jsonl"
    lines = target.read_text(encoding="utf-8").splitlines()
    body = json.loads(lines[0])
    body["outputs"]["probability_above_threshold"] = 1.0
    lines[0] = json.dumps(body, sort_keys=True, separators=(",", ":"))
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")

    verify = _cli("history", "--verify", cwd=tmp_path)
    assert verify.returncode == 1
    assert "CHAIN BROKEN" in verify.stderr

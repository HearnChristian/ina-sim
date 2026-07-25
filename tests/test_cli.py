"""Every subcommand, driven in-process through main().

These call `ina_sim.cli.main([...])` directly rather than spawning a subprocess.
Two reasons: it is an order of magnitude faster, and subprocess tests report
zero coverage for the CLI, which had left the largest module in the package
looking untested when it was merely unmeasured.

The contract each test holds the CLI to is narrow and deliberate: exit 0 on
success, exit 1 on bad input, a usable message on stderr rather than a
traceback, and valid JSON whenever --json is passed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ina_sim.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ASSAY = REPO_ROOT / "examples" / "kfeldspar_synthetic_assay.csv"


@pytest.fixture(autouse=True)
def _isolated_run_log(tmp_path, monkeypatch):
    """Never write to the developer's real audit log from a test."""
    monkeypatch.setenv("INA_SIM_RUN_LOG", str(tmp_path / "runs.jsonl"))


def run(*args: str) -> int:
    return main(list(args))


def json_out(capsys, *args: str):
    assert run(*args) == 0
    return json.loads(capsys.readouterr().out)


# --- Every command runs ----------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ("list",),
        ("screen", "--temp", "-15"),
        ("screen", "--temp", "-15", "--track", "warm_cloud"),
        ("show", "agi"),
        ("ns", "--list"),
        ("ns", "--temp", "-20"),
        ("ns", "--temp", "-20", "--candidate", "k_feldspar"),
        ("freeze", "--id", "k_feldspar_harrison2019"),
        ("freeze", "--id", "water_homogeneous_murray2010"),
        ("assay", str(EXAMPLE_ASSAY)),
        ("aerosol", "--id", "desert_dust_niemand2012", "--mode", "1:0.8:1.9"),
        ("compare", "--temp", "-20"),
        ("rank", "--temp", "-20"),
        ("uncertainty", "--id", "k_feldspar_harrison2019", "--mode", "1:0.8:1.9",
         "--samples", "300"),
        ("scenario", "--id", "agi_marcolli2016_derived", "--payload-kg", "1",
         "--diameter", "0.1", "--samples", "300"),
        ("validate",),
        ("refs",),
        ("refs", "--key", "harrison2019"),
        ("doctor",),
        ("uploads",),
    ],
)
def test_command_exits_zero(argv, capsys):
    assert run(*argv) == 0
    assert capsys.readouterr().out.strip()


@pytest.mark.parametrize(
    "argv",
    [
        ("screen", "--temp", "-15", "--json"),
        ("ns", "--temp", "-20", "--json"),
        ("ns", "--list", "--json"),
        ("freeze", "--id", "k_feldspar_harrison2019", "--json"),
        ("assay", str(EXAMPLE_ASSAY), "--json"),
        ("aerosol", "--id", "desert_dust_niemand2012", "--mode", "1:0.8:1.9", "--json"),
        ("compare", "--temp", "-20", "--json"),
        ("rank", "--temp", "-20", "--json"),
        ("uncertainty", "--id", "k_feldspar_harrison2019", "--mode", "1:0.8:1.9",
         "--samples", "300", "--json"),
        ("scenario", "--id", "agi_marcolli2016_derived", "--payload-kg", "1",
         "--diameter", "0.1", "--samples", "300", "--json"),
        ("validate", "--json"),
        ("refs", "--json"),
        ("doctor", "--json"),
    ],
)
def test_json_output_parses(argv, capsys):
    payload = json_out(capsys, *argv)
    assert payload not in (None, {}, [])


# --- Bad input is refused cleanly, never with a traceback ------------------


@pytest.mark.parametrize(
    "argv,fragment",
    [
        (("ns", "--id", "no_such_fit"), "unknown parameterization"),
        (("freeze", "--id", "no_such_fit"), "unknown parameterization"),
        (("refs", "--key", "no_such_paper"), "unknown reference"),
        (("assay", "/nonexistent/file.csv"), "no such file"),
        (("aerosol", "--id", "desert_dust_niemand2012", "--mode", "bad"), "mode"),
        (("aerosol", "--id", "kaolinite_murray2011", "--mode", "1:1:1.5"), "rate"),
        (("compare", "--range=not:a:range"), "lo:hi:step"),
        (("uncertainty", "--id", "kaolinite_murray2011", "--mode", "1:1:1.5"), "ns"),
        (("scenario", "--id", "agi_marcolli2016_derived"), "exactly one"),
        (("scenario", "--id", "quartz_harrison2019", "--payload-kg", "1"), "density"),
        (("ns", "--candidate", "not_a_candidate"), "No parameterization"),
    ],
)
def test_bad_input_exits_one_with_a_message(argv, fragment, capsys):
    assert run(*argv) == 1
    err = capsys.readouterr().err
    assert fragment.lower() in err.lower()
    assert "Traceback" not in err


def test_screen_clamps_an_impossible_temperature_and_says_so(capsys):
    """Out-of-envelope inputs are clamped rather than rejected, but the clamp is
    always reported — a silent clamp would be the problem."""
    assert run("screen", "--temp", "500") == 0
    out = capsys.readouterr()
    assert "clamped" in out.out
    assert "Traceback" not in out.err


# --- Behaviour worth pinning ----------------------------------------------


def test_screen_json_carries_provenance_and_evidence(capsys):
    payload = json_out(capsys, "screen", "--temp", "-15", "--json")
    assert payload["provenance"]["param_hash"]
    assert payload["empirical_layer"]["validation"]["ok"] is True
    assert payload["results"][0]["evidence"]["evidence"] in {
        "measured", "solute", "none"
    }


def test_ns_withholds_values_outside_the_fitted_range(capsys):
    payload = json_out(capsys, "ns", "--temp", "-2", "--id", "quartz_harrison2019",
                       "--json")
    assert payload[0]["value"] is None
    assert payload[0]["in_range"] is False


def test_ns_extrapolates_only_when_asked(capsys):
    payload = json_out(capsys, "ns", "--temp", "-2", "--id", "quartz_harrison2019",
                       "--extrapolate", "--json")
    assert payload[0]["value"] is not None
    assert payload[0]["extrapolated"] is True


def test_scenario_writes_to_the_audit_log_and_history_reads_it(capsys, tmp_path):
    assert run("scenario", "--id", "agi_marcolli2016_derived", "--payload-kg", "1",
               "--diameter", "0.1", "--samples", "300") == 0
    capsys.readouterr()
    assert run("history") == 0
    assert "scenario" in capsys.readouterr().out
    assert run("history", "--verify") == 0
    assert "intact" in capsys.readouterr().out


def test_scenario_can_opt_out_of_logging(capsys, tmp_path, monkeypatch):
    target = tmp_path / "nothing.jsonl"
    monkeypatch.setenv("INA_SIM_RUN_LOG", str(target))
    assert run("scenario", "--id", "agi_marcolli2016_derived", "--payload-kg", "1",
               "--diameter", "0.1", "--samples", "300", "--no-log") == 0
    assert not target.exists()


def test_history_on_an_empty_log_is_not_an_error(capsys):
    assert run("history") == 0
    assert "No runs logged" in capsys.readouterr().out


def test_assay_writes_a_spectrum_file(tmp_path, capsys):
    out = tmp_path / "spectrum.csv"
    assert run("assay", str(EXAMPLE_ASSAY), "--out", str(out)) == 0
    assert out.is_file()
    assert out.read_text(encoding="utf-8").startswith("T_c,")


def test_figures_command_writes_a_page(tmp_path, capsys):
    out = tmp_path / "figs.html"
    assert run("figures", "--out", str(out)) == 0
    assert out.read_text(encoding="utf-8").count("<svg") >= 9


def test_screen_can_write_json_to_a_file(tmp_path, capsys):
    out = tmp_path / "screen.json"
    assert run("screen", "--temp", "-15", "--out", str(out)) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["results"]


def test_doctor_reports_every_check(capsys):
    payload = json_out(capsys, "doctor", "--json")
    names = {c["name"] for c in payload["checks"]}
    assert names == {
        "environment", "registry", "validation", "derived fits",
        "documentation", "audit log",
    }
    assert payload["ok"] is True


def test_doctor_fails_when_the_audit_chain_is_broken(capsys, tmp_path, monkeypatch):
    target = tmp_path / "runs.jsonl"
    monkeypatch.setenv("INA_SIM_RUN_LOG", str(target))
    run("scenario", "--id", "agi_marcolli2016_derived", "--payload-kg", "1",
        "--diameter", "0.1", "--samples", "300")
    capsys.readouterr()

    body = json.loads(target.read_text(encoding="utf-8").splitlines()[0])
    body["outputs"]["probability_above_threshold"] = 1.0
    target.write_text(json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n",
                      encoding="utf-8")

    assert run("doctor") == 1
    assert "FAIL" in capsys.readouterr().out


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exit_info:
        run("--version")
    assert exit_info.value.code == 0
    assert "ina-sim" in capsys.readouterr().out


def test_every_subcommand_has_help(capsys):
    for command in (
        "list", "screen", "show", "ns", "freeze", "assay", "aerosol", "compare",
        "rank", "uncertainty", "scenario", "history", "doctor", "validate",
        "refs", "figures", "gui", "upload", "uploads",
    ):
        with pytest.raises(SystemExit) as exit_info:
            run(command, "--help")
        assert exit_info.value.code == 0
        assert capsys.readouterr().out.strip(), f"{command} has no help text"

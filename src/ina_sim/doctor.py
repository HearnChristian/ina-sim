"""One command that answers "can I trust this build?".

Everything needed to decide that already exists, scattered across the validation
runner, the derived-fit checker, the docs generator and the audit log. Somebody
evaluating this repository - or picking it up after six months away - should not
have to know that. `ina-sim doctor` runs every self-check there is and exits
non-zero if any of them fails.

Each check answers a specific question about trustworthiness:

    environment      does the package import, and is its version coherent?
    registry         does every parameterization load, cite a real reference,
                     and stay monotonic across its own validity range?
    validation       does this build still reproduce the published claims?
    derived fits     does the AgI fit still match the dataset it came from?
    documentation    do the generated docs describe this build or an older one?
    audit log        is the run log's hash chain intact?

A green doctor is not a claim that the science is right. It is a claim that the
build is internally consistent with the sources it cites, which is the most a
tool can check about itself.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ina_sim import __version__


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # pass | fail | skip
    detail: str
    remedy: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "remedy": self.remedy,
        }


def _repo_root() -> Path | None:
    """The source checkout, when running from one. None when pip-installed."""
    candidate = Path(__file__).resolve().parents[2]
    return candidate if (candidate / "pyproject.toml").is_file() else None


def check_environment() -> Check:
    try:
        import yaml  # noqa: F401
    except ImportError:
        return Check(
            "environment",
            "fail",
            "PyYAML is not installed",
            "pip install -e .",
        )
    if sys.version_info < (3, 11):
        return Check(
            "environment",
            "fail",
            f"Python {sys.version_info.major}.{sys.version_info.minor} is too old",
            "this package requires Python 3.11 or newer",
        )
    return Check(
        "environment",
        "pass",
        f"INA-sim {__version__} on Python "
        f"{sys.version_info.major}.{sys.version_info.minor}, PyYAML present",
    )


def check_registry() -> Check:
    """Load every parameterization and re-derive its basic invariants."""
    from ina_sim.physics.ns import evaluate, load_parameterizations
    from ina_sim.references import load_references

    try:
        params = load_parameterizations()
        references = load_references()
    except Exception as exc:  # noqa: BLE001 - report, do not crash
        return Check("registry", "fail", f"could not load: {exc}", "check the YAML files")

    problems: list[str] = []
    for param in params.values():
        if param.reference not in references:
            problems.append(f"{param.id} cites unknown reference {param.reference!r}")
        previous = None
        for i in range(21):
            temp = param.t_max_c - (param.t_max_c - param.t_min_c) * i / 20
            est = evaluate(param, temp)
            if est.value is None:
                problems.append(f"{param.id} returned nothing inside its own range")
                break
            if previous is not None and est.value <= previous:
                problems.append(f"{param.id} is not monotonic at {temp:.1f} C")
                break
            previous = est.value

    if problems:
        return Check(
            "registry",
            "fail",
            "; ".join(problems[:4]),
            "fix library/parameterizations.yaml or library/references.yaml",
        )
    published = sum(1 for p in params.values() if p.status == "published")
    return Check(
        "registry",
        "pass",
        f"{len(params)} parameterizations ({published} published, "
        f"{len(params) - published} derived), all cited and monotonic",
    )


def check_validation() -> Check:
    from ina_sim.validation.runner import run_validation

    try:
        report = run_validation()
    except Exception as exc:  # noqa: BLE001
        return Check("validation", "fail", f"suite did not run: {exc}", "ina-sim validate")
    if not report.ok:
        failures = "; ".join(r.id for r in report.results if r.status == "fail")
        return Check(
            "validation",
            "fail",
            f"{report.n_fail} anchor(s) failed: {failures}",
            "ina-sim validate  (do not quote numbers from this build)",
        )
    return Check(
        "validation",
        "pass",
        f"{report.n_pass} published claims reproduced, {report.n_fail} failed",
    )


def _run_tool(script: str, args: list[str]) -> tuple[bool, str]:
    root = _repo_root()
    if root is None:
        return True, "not a source checkout"
    path = root / "tools" / script
    if not path.is_file():
        return True, f"{script} not present"
    proc = subprocess.run(
        [sys.executable, str(path), *args],
        capture_output=True,
        text=True,
        cwd=root,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip().splitlines()[-1]


def check_derived_fits() -> Check:
    ok, detail = _run_tool("fit_agi_ns.py", ["--check"])
    if detail == "not a source checkout":
        return Check(
            "derived fits", "skip", "installed package: the fitting tools are not shipped"
        )
    return Check(
        "derived fits",
        "pass" if ok else "fail",
        detail,
        None if ok else "python tools/fit_agi_ns.py --yaml",
    )


def check_docs() -> Check:
    ok, detail = _run_tool("gen_docs.py", ["--check"])
    if detail == "not a source checkout":
        return Check("documentation", "skip", "installed package: docs are not shipped")
    return Check(
        "documentation",
        "pass" if ok else "fail",
        detail,
        None if ok else "python tools/gen_docs.py",
    )


def check_audit_log() -> Check:
    from ina_sim.audit import log_path, read_records, verify_chain

    target = log_path()
    if not target.is_file():
        return Check("audit log", "skip", f"no run log yet at {target}")
    try:
        records = read_records(target)
    except Exception as exc:  # noqa: BLE001
        return Check("audit log", "fail", str(exc), "inspect the log by hand")
    problems = verify_chain(records)
    if problems:
        return Check(
            "audit log",
            "fail",
            f"{len(problems)} chain problem(s); first: {problems[0].detail}",
            "ina-sim history --verify",
        )
    return Check("audit log", "pass", f"{len(records)} records, hash chain intact")


CHECKS: tuple[Callable[[], Check], ...] = (
    check_environment,
    check_registry,
    check_validation,
    check_derived_fits,
    check_docs,
    check_audit_log,
)


def run_doctor() -> list[Check]:
    results: list[Check] = []
    for check in CHECKS:
        try:
            results.append(check())
        except Exception as exc:  # noqa: BLE001 - a broken check is a failed check
            results.append(
                Check(check.__name__, "fail", f"check itself raised: {exc}")
            )
    return results


def format_report(checks: list[Check]) -> str:
    lines = [f"INA-sim {__version__} — self-check", ""]
    for check in checks:
        mark = {"pass": "  ok ", "fail": "FAIL ", "skip": "skip "}[check.status]
        lines.append(f"{mark} {check.name:<15} {check.detail}")
        if check.remedy:
            lines.append(f"       {'':<15} → {check.remedy}")
    failed = [c for c in checks if c.status == "fail"]
    lines.append("")
    if failed:
        lines.append(
            f"{len(failed)} check(s) failed. This build is not internally "
            "consistent — do not quote numbers from it."
        )
    else:
        lines.append(
            "All checks passed. Every number this build reports traces to a "
            "cited source, and it still reproduces the claims it makes."
        )
    return "\n".join(lines)

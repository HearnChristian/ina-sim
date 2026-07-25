"""Append-only, tamper-evident record of every run.

Weather modification gets challenged - by regulators, by neighbours, by
opposing counsel - and the question is rarely "what does your model say" but
"what did your model say on the fourteenth, and has anything changed since".
A tool that cannot answer that is not usable in the field.

Every logged run records its inputs, its headline outputs, the code version,
whether the self-checks passed, and a **registry fingerprint**: the hash of
`library/parameterizations.yaml`. That last field is what makes the log worth
keeping. When a number moves between two runs, the log distinguishes

    the conditions changed          (different temperature, payload, aerosol)
    the science changed             (a parameterization was updated)
    nothing changed and the number moved  (a bug, and now you can prove it)

Records are chained: each carries the hash of the one before it, so removing or
editing an entry breaks every hash after it and `ina-sim history --verify` says
so. This is tamper *evident*, not tamper proof - anyone who can rewrite the file
can recompute the chain. It defends against accident and quiet edits, which is
what actually happens, not against a determined forger.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ina_sim import __version__

ENV_PATH = "INA_SIM_RUN_LOG"
ENV_DISABLE = "INA_SIM_NO_RUN_LOG"
DEFAULT_RELATIVE = Path("data") / "runs" / "log.jsonl"

GENESIS = "0" * 32
HASH_LENGTH = 32


class AuditError(RuntimeError):
    """Raised when the run log cannot be read or is internally inconsistent."""


def log_path() -> Path:
    """Where the run log lives. Override with INA_SIM_RUN_LOG."""
    override = os.environ.get(ENV_PATH)
    if override:
        return Path(override).expanduser()
    return Path.cwd() / DEFAULT_RELATIVE


def logging_enabled() -> bool:
    return os.environ.get(ENV_DISABLE, "").strip().lower() not in {"1", "true", "yes"}


def _canonical(body: dict[str, Any]) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)


def record_hash(body: dict[str, Any]) -> str:
    """Hash of a record, excluding the hash field itself."""
    payload = {k: v for k, v in body.items() if k != "record_hash"}
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()[:HASH_LENGTH]


def registry_fingerprint() -> str:
    """Hash of the parameterization file: identifies the science in use."""
    from importlib import resources

    ref = resources.files("ina_sim.library").joinpath("parameterizations.yaml")
    return hashlib.sha256(ref.read_bytes()).hexdigest()[:HASH_LENGTH]


@dataclass(frozen=True)
class RunRecord:
    index: int
    timestamp_utc: str
    command: str
    version: str
    registry_fingerprint: str
    validation_ok: bool | None
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    prev_hash: str
    record_hash: str
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "timestamp_utc": self.timestamp_utc,
            "command": self.command,
            "version": self.version,
            "registry_fingerprint": self.registry_fingerprint,
            "validation_ok": self.validation_ok,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "note": self.note,
            "prev_hash": self.prev_hash,
            "record_hash": self.record_hash,
        }


def read_records(path: Path | None = None) -> list[RunRecord]:
    target = path or log_path()
    if not target.is_file():
        return []
    records: list[RunRecord] = []
    for line_number, line in enumerate(
        target.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            body = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AuditError(f"{target}:{line_number}: not valid JSON ({exc})") from exc
        records.append(
            RunRecord(
                index=int(body.get("index", line_number - 1)),
                timestamp_utc=str(body.get("timestamp_utc", "")),
                command=str(body.get("command", "")),
                version=str(body.get("version", "")),
                registry_fingerprint=str(body.get("registry_fingerprint", "")),
                validation_ok=body.get("validation_ok"),
                inputs=body.get("inputs") or {},
                outputs=body.get("outputs") or {},
                prev_hash=str(body.get("prev_hash", GENESIS)),
                record_hash=str(body.get("record_hash", "")),
                note=body.get("note"),
            )
        )
    return records


def append_run(
    command: str,
    *,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    validation_ok: bool | None = None,
    note: str | None = None,
    path: Path | None = None,
) -> RunRecord | None:
    """Append one record. Returns None when logging is disabled.

    Never raises on a write failure: a broken log must not take down a
    calculation someone is in the middle of. Failures surface through
    `ina-sim history --verify` instead.
    """
    if not logging_enabled():
        return None
    target = path or log_path()
    try:
        existing = read_records(target)
    except AuditError:
        existing = []
    prev = existing[-1].record_hash if existing else GENESIS

    body: dict[str, Any] = {
        "index": len(existing),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": command,
        "version": __version__,
        "registry_fingerprint": registry_fingerprint(),
        "validation_ok": validation_ok,
        "inputs": inputs,
        "outputs": outputs,
        "note": note,
        "prev_hash": prev,
    }
    body["record_hash"] = record_hash(body)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(_canonical(body) + "\n")
    except OSError:
        return None

    return RunRecord(
        index=body["index"],
        timestamp_utc=body["timestamp_utc"],
        command=command,
        version=body["version"],
        registry_fingerprint=body["registry_fingerprint"],
        validation_ok=validation_ok,
        inputs=inputs,
        outputs=outputs,
        prev_hash=prev,
        record_hash=body["record_hash"],
        note=note,
    )


@dataclass(frozen=True)
class ChainProblem:
    index: int
    kind: str  # broken_link | bad_hash | bad_index
    detail: str


def verify_chain(records: list[RunRecord]) -> list[ChainProblem]:
    """Recompute the chain. An empty list means the log is internally intact."""
    problems: list[ChainProblem] = []
    expected_prev = GENESIS
    for position, record in enumerate(records):
        if record.index != position:
            problems.append(
                ChainProblem(
                    position,
                    "bad_index",
                    f"record says index {record.index}, found at position {position}"
                    " — an entry was probably removed",
                )
            )
        if record.prev_hash != expected_prev:
            problems.append(
                ChainProblem(
                    position,
                    "broken_link",
                    f"prev_hash {record.prev_hash[:12]}… does not match the "
                    f"previous record's hash {expected_prev[:12]}…",
                )
            )
        recomputed = record_hash(record.as_dict())
        if recomputed != record.record_hash:
            problems.append(
                ChainProblem(
                    position,
                    "bad_hash",
                    f"contents do not match their hash (stored "
                    f"{record.record_hash[:12]}…, recomputed {recomputed[:12]}…)"
                    " — this record was edited after it was written",
                )
            )
        expected_prev = record.record_hash
    return problems


def _flatten(body: dict[str, Any], prefix: str = "") -> Iterator[tuple[str, Any]]:
    for key, value in body.items():
        label = f"{prefix}{key}"
        if isinstance(value, dict):
            yield from _flatten(value, f"{label}.")
        else:
            yield label, value


def diff_runs(before: RunRecord, after: RunRecord) -> dict[str, Any]:
    """Explain why two runs differ, separating conditions from science."""
    changed_inputs: dict[str, Any] = {}
    for scope, older, newer in (
        ("inputs", before.inputs, after.inputs),
        ("outputs", before.outputs, after.outputs),
    ):
        old_flat = dict(_flatten(older))
        new_flat = dict(_flatten(newer))
        entries = {}
        for key in sorted(set(old_flat) | set(new_flat)):
            old_value, new_value = old_flat.get(key), new_flat.get(key)
            if old_value != new_value:
                entries[key] = {"before": old_value, "after": new_value}
        changed_inputs[scope] = entries

    science_changed = before.registry_fingerprint != after.registry_fingerprint
    code_changed = before.version != after.version
    inputs_changed = bool(changed_inputs["inputs"])
    outputs_changed = bool(changed_inputs["outputs"])

    if not outputs_changed:
        verdict = "outputs identical"
    elif inputs_changed and not science_changed and not code_changed:
        verdict = "the conditions changed"
    elif science_changed and not inputs_changed:
        verdict = "the science changed: a parameterization was edited between these runs"
    elif science_changed and inputs_changed:
        verdict = "both the conditions and the parameterizations changed"
    elif code_changed:
        verdict = f"the code changed ({before.version} → {after.version})"
    else:
        verdict = (
            "outputs moved with identical inputs, identical parameterizations and "
            "identical code — this should not happen and is worth investigating"
        )

    return {
        "before": {"index": before.index, "at": before.timestamp_utc},
        "after": {"index": after.index, "at": after.timestamp_utc},
        "registry_changed": science_changed,
        "code_changed": code_changed,
        "verdict": verdict,
        "changed": changed_inputs,
    }


def summarise(records: list[RunRecord]) -> dict[str, Any]:
    fingerprints = {r.registry_fingerprint for r in records}
    return {
        "n_runs": len(records),
        "commands": sorted({r.command for r in records}),
        "first": records[0].timestamp_utc if records else None,
        "last": records[-1].timestamp_utc if records else None,
        "distinct_registry_versions": len(fingerprints),
        "current_registry": registry_fingerprint(),
        "runs_on_current_registry": sum(
            1 for r in records if r.registry_fingerprint == registry_fingerprint()
        ),
        "runs_with_failing_validation": sum(
            1 for r in records if r.validation_ok is False
        ),
    }

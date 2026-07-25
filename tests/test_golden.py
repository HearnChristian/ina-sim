"""Golden snapshot tests — catch silent ranking flips in CI."""

from __future__ import annotations

import json
from pathlib import Path

from ina_sim.gui.server import run_screen_payload
from ina_sim.schema import assert_screen_payload

FIXTURE = Path(__file__).parent / "fixtures" / "screen_starter_T-10.json"


def test_golden_starter_screen_minus10():
    payload = run_screen_payload(temperature_c=-10.0, starter_set=True)
    assert_screen_payload(payload)
    gold = json.loads(FIXTURE.read_text(encoding="utf-8"))
    got_ids = [r["id"] for r in payload["results"]]
    want_ids = [r["id"] for r in gold["results"]]
    assert got_ids == want_ids, f"rank order changed: {got_ids} vs {want_ids}"
    for g, r in zip(gold["results"], payload["results"], strict=True):
        assert r["id"] == g["id"]
        assert r["class"] == g["class"]
        assert r["pathway"] == g["pathway"]
        assert abs(r["relative_ina"] - g["relative_ina"]) < 1e-3
        assert r["confidence"] == g["confidence"]
    assert payload["literature_xref"]["summary"]["ok"] is gold["literature_xref_ok"]
    assert payload["baseline"] == gold["baseline"]


def test_schema_rejects_missing_keys():
    from ina_sim.schema import validate_screen_payload

    errs = validate_screen_payload({"version": "0"})
    assert errs

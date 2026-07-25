# Professional & robust upgrade roadmap

**Recorded:** 2026-07-24  
**Status:** Implemented in the same change set (see `docs/PROJECT.md` §13).  
**Source:** Product review — “what would make this more professional and robust?”

This file is the permanent checklist of suggestions. Items marked **DONE** ship in-tree; **NEXT** remain for molecular builder / L2 MD.

---

## 1. Scientific credibility

| # | Suggestion | Status |
|---|------------|--------|
| 1.1 | Cite every η curve — source visible in UI row / JSON | **DONE** (`source`, `citation` fields) |
| 1.2 | Calibrate directionally to published activity vs T (AgI, feldspar, kaolinite) | **DONE** (`library/activity_curves.yaml` + `physics/activity.py`) |
| 1.3 | Separate ice vs hygroscopic / warm-cloud tracks completely + banner | **DONE** (`track=ice\|warm_cloud`) |
| 1.4 | Uncertainty bands on relINA | **DONE** (`relative_ina_low` / `high`) |
| 1.5 | Version + param hash + assumptions in every export | **DONE** (`provenance` block) |

## 2. Software robustness

| # | Suggestion | Status |
|---|------------|--------|
| 2.1 | Disable controls while screen in flight | **DONE** (GUI) |
| 2.2 | Golden JSON fixtures for CI | **DONE** (`tests/fixtures/`, `test_golden.py`) |
| 2.3 | Property tests (bounds, vapor ≥ 0, ranking controls) | **DONE** (`test_properties.py`) |
| 2.4 | Request/response schema validation | **DONE** (`ina_sim/schema.py`, no new deps) |
| 2.5 | Report clamps explicitly (original vs used) | **DONE** (`conditions_requested` / `conditions_used` / `clamped`) |
| 2.6 | Dev tooling: ruff/mypy optional + lockfile note | **DONE** (`pyproject.toml` extras, `requirements-dev.txt`) |
| 2.7 | GitHub Actions pytest | **DONE** (`.github/workflows/ci.yml`) |

## 3. Product polish

| # | Suggestion | Status |
|---|------------|--------|
| 3.1 | 90-second demo script | **DONE** (`docs/DEMO-SCRIPT.md`) |
| 3.2 | One-pager (mission, assumptions, limitations) | **DONE** (`docs/ONE-PAGER.md`) |
| 3.3 | Always-visible assumptions panel | **DONE** (GUI) |
| 3.4 | Remove testosterone from default library | **DONE** (moved to experimental YAML, not loaded by default) |
| 3.5 | README “what this is not” + architecture pointer | **DONE** |

## 4. Physics leveling

| # | Suggestion | Status |
|---|------------|--------|
| 4.1 | Table-driven immersion activity vs T | **DONE** (directional, not ns(T) absolute) |
| 4.2 | CNT remains secondary column only | **DONE** (unchanged intent; rank default = relINA) |
| 4.3 | Warm-cloud / hygroscopic as separate track | **DONE** |
| 4.4 | Molecular builder | **NEXT** (upload feed already exists) |
| 4.5 | L2 MD | **NEXT** |

## 5. Process

| # | Suggestion | Status |
|---|------------|--------|
| 5.1 | Living changelog in PROJECT.md | **DONE** (maintain) |
| 5.2 | CONTRIBUTING + scientific disclaimer | **DONE** |
| 5.3 | Issue templates / labels doc | **DONE** (`.github/ISSUE_TEMPLATE/`, `docs/ISSUE-LABELS.md`) |

---

## Explicit non-goals (still)

- Absolute operational nucleation rates  
- Payload sales claims without wet-lab  
- Live-on-drag ranking  
- Sexy 3D before calibration  

---

## Still missing for “extremely passable research element” (human reviewer)

Do **not** bloat the GUI for these — they are credibility / process, not more chrome:

1. **Named citations on every activity table** (DOI or standard citation string in `activity_curves.yaml` — partially present; tighten to real paper IDs).  
2. **Sensitivity one-pager** — one figure: score vs T for AgI/feldspar/kaolinite with band, exported from T-sweep.  
3. **Methods paragraph** you can paste into a README/poster (assumptions + what is not claimed).  
4. **Independent re-run** — another machine / clean venv, same param_hash.  
5. **Comparison table** to 1–2 published onset temperatures (qualitative “warmer/colder than”), not fake ns(T).  
6. **Remove remaining jargon from status line** where possible (done for banner/track).  
7. **Human test** — hand laptop to a non-author for 5 minutes; if they ask “what is starter set / CCN?” you failed labels (addressed).  

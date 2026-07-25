---
name: ina-sim
description: >
  Work on the INA-sim ice-nucleating agent screening lab (Rainmaker-track learning lab).
  Use when the user mentions INA-sim, ina-sim, ice nucleation, cloud seeding agents,
  Rainmaker portfolio sim, molecular uploads for INA, or runs /ina-sim.
  Always read docs/PROJECT.md first and keep it updated when behavior changes.
---

# INA-sim skill

## First actions every session

1. Read `docs/PROJECT.md` (living handbook) — it is source of truth for mission, UX, APIs.
2. Skim `docs/PROFESSIONAL-ROADMAP.md` for DONE vs NEXT professional checklist.
3. Work in repo root `ina-sim/` (or `~/ina-sim`).
4. Prefer existing modules over new frameworks. **No new heavy deps** unless asked (offline-first, stdlib + pyyaml).

## Product rules (do not violate)

- **60% learning lab / 40% portfolio** — not a product to sell.
- Numbers = honest ranges + confidence tiers; never operational weather-control claims.
- Uploads = **exploratory** / placeholder η until molecular builder exists.
- Hygroscopics ≠ ice nucleants (warn and pathway label).
- After meaningful changes: update `docs/PROJECT.md` changelog (§13) and relevant sections.
- Literature intent: keep `docs/LITERATURE-CHECKS.md` + `physics/research_xref.py` aligned with ranking.

## GUI UX (locked)

- Sliders update **labels only** while dragging.
- **Run Screen** is the primary apply action.
- Live update **off by default**; if enabled, run only on slider **release** (`change`), never on every `input`.
- Results must fingerprint conditions; mark UI stale when controls diverge from last run.
- Export JSON = File menu only.
- Offline local server only (`ina-sim gui`).

## Common commands

```bash
cd ~/ina-sim && source .venv/bin/activate
ina-sim screen --temp -10 --tag starter-set
ina-sim gui --no-browser
ina-sim upload --smiles CCO --name Ethanol
pytest -q
```

## Where to edit

| Task | Location |
|------|----------|
| Atmosphere / thermo | `src/ina_sim/physics/atmosphere.py` |
| Efficiency / modes | `src/ina_sim/physics/efficiency.py` |
| CNT | `src/ina_sim/physics/cnt.py` |
| Literature checks | `src/ina_sim/physics/research_xref.py`, `docs/LITERATURE-CHECKS.md` |
| Library agents | `src/ina_sim/library/candidates.yaml` |
| Uploads / builder feed | `src/ina_sim/library/molecular.py`, `registry.py` |
| Screen pipeline | `src/ina_sim/screen/rank.py` |
| GUI server | `src/ina_sim/gui/server.py` |
| GUI front | `src/ina_sim/gui/static/index.html` |
| Mission | `docs/REFLECTION-LOCK-2026-07-24.md` |

## Before finishing

1. `pytest -q`  
2. Update `docs/PROJECT.md` if behavior/docs/APIs changed  
3. If ranking order vs literature changes, fix YAML/physics or update literature docs with cited reason  

## ADHD output

Lead with next action; number steps; keep responses short; show what works.

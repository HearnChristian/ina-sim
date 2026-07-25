# Contributing to INA-sim

## Scientific software disclaimer

INA-sim is a **personal learning lab / portfolio tool**. It is **not**:

- Operational weather-modification software  
- A calibrated source of ice-nucleating particle (INP) concentrations  
- Advice for field seeding, aviation, or regulatory decisions  

All rankings are **heuristic and directional**. Uncertainty bands and literature cross-checks are teaching aids. Wet-lab or supplier data is required before any real payload spend.

By contributing, you agree not to present model output as operational truth.

## Dev setup

```bash
cd ina-sim
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Optional: `ruff check src tests`, `mypy src/ina_sim`.

## Rules of the road

1. Read `docs/PROJECT.md` and `docs/PROFESSIONAL-ROADMAP.md`.  
2. Prefer stdlib + PyYAML; justify new dependencies.  
3. If ranking vs literature changes, update `docs/LITERATURE-CHECKS.md` and golden fixtures.  
4. Keep GUI offline-first (`ina-sim gui`).  
5. Uploads stay **exploratory**.  
6. Update `docs/PROJECT.md` changelog when behavior changes.  

## Tests that must stay green

- Literature + research xref  
- Golden screen snapshot (`tests/fixtures/`)  
- Property bounds / warm-cloud track  

## Issue labels

See `docs/ISSUE-LABELS.md`.

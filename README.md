# INA-sim

**Local multi-fidelity ice nucleation agent (INA) screening lab** — Rainmaker-track literacy, alternative INA exploration, honest confidence scores.

> **60% learning lab · 40% portfolio.** Not a product to sell. Not operational weather control. Not absolute nucleation rates.

**Living handbook:** [`docs/PROJECT.md`](docs/PROJECT.md)  
**Professional checklist:** [`docs/PROFESSIONAL-ROADMAP.md`](docs/PROFESSIONAL-ROADMAP.md)  
**One-pager:** [`docs/ONE-PAGER.md`](docs/ONE-PAGER.md) · **Demo:** [`docs/DEMO-SCRIPT.md`](docs/DEMO-SCRIPT.md)  
**Literature:** [`docs/LITERATURE-CHECKS.md`](docs/LITERATURE-CHECKS.md)  
**Skill:** `.grok/skills/ina-sim/`

## What this is not

- Not calibrated \(n_s(T)\) or field INP measurements  
- Not cloud-resolving / radar verification  
- Not operational seeding guidance or a commercial product  
- Not a substitute for wet-lab validation before any payload spend  

## Status (v0.2)

| Layer | State |
|-------|--------|
| **L0/L1 + activity tables** | Working (CLI + GUI) |
| **Atmosphere** | Water + ice Magnus, S_w / S_i, RH_ice |
| **CNT (educational)** | Secondary score only |
| **Tracks** | `ice` (glaciogenic) vs `warm_cloud` (CCN) |
| **Literature xref** | Directional public-research checks on every screen |
| **Uncertainty bands** | Confidence-tier relINA low–high |
| **Provenance** | version, param_hash, assumptions, clamp report |
| **Molecular uploads** | SMILES/XYZ/MOL/JSON → exploratory builder feed |
| **GUI** | Win95 chrome, assumptions panel, mechanism banner |
| **CI** | GitHub Actions + golden fixtures |
| **L2 MD / molecular builder** | Next |

```
Candidate library → track + conditions → activity tables / heuristics
  → rank + bands + sources → literature_xref + provenance export
```

## Quick start

```bash
cd ina-sim
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

ina-sim list
ina-sim screen --temp -10 --tag starter-set
ina-sim screen --temp 0 --track warm_cloud
ina-sim upload --smiles CCO --name Ethanol
ina-sim gui                    # http://127.0.0.1:8765/
pytest -q
```

## Architecture pointer

```
src/ina_sim/
  physics/     atmosphere, activity tables, efficiency, CNT, research_xref
  library/     candidates.yaml, activity_curves.yaml, molecular uploads
  screen/      rank + uncertainty
  provenance.py  param_hash + assumptions
  schema.py      payload validation
  gui/         offline stdlib server + Win95 HTML
docs/          PROJECT.md (keep updated)
tests/         literature, golden, properties, stress
```

## License

MIT — see [LICENSE](LICENSE). Scientific disclaimer: [CONTRIBUTING.md](CONTRIBUTING.md).

# INA-sim

**Local multi-fidelity ice nucleation agent (INA) screening lab** — Rainmaker-track literacy, alternative INA exploration, honest confidence scores.

> **60% learning lab · 40% portfolio.** Not a product to sell. Not operational weather control. Not absolute nucleation rates.

**Methods (every equation, unit and source):** [`docs/METHODS.md`](docs/METHODS.md)
**Validation (what this build reproduces):** [`docs/VALIDATION.md`](docs/VALIDATION.md)
**Bibliography:** [`docs/REFERENCES.md`](docs/REFERENCES.md) · **Wanted:** [`docs/PAPERS-WANTED.md`](docs/PAPERS-WANTED.md)
**Living handbook:** [`docs/PROJECT.md`](docs/PROJECT.md) · **Demo:** [`docs/DEMO-SCRIPT.md`](docs/DEMO-SCRIPT.md)

## Two layers, kept apart on purpose

| | heuristic layer | empirical layer |
|---|---|---|
| answers | "which would I try first?" | "what has anyone measured?" |
| output | relative score 0–1 vs AgI | ns(T) in m⁻², J(T), frozen fraction, T50 |
| basis | shaped activity curves | published fits, with DOI, units, validity range and σ |
| honest use | ordering a shortlist | quoting a number |

The relative score is a ranking convention. The empirical layer is evidence.
Every screen labels which candidates have either.

```bash
ina-sim ns --list                  # what is actually parameterized, and by whom
ina-sim ns --temp -20              # ns(T) / J(T) from the literature
ina-sim assay my_run.csv           # YOUR droplet-freezing data -> ns(T) + comparison
ina-sim aerosol --id desert_dust_niemand2012 --mode 1:0.8:1.9 --temp -20
ina-sim compare --range=-35:-10:5  # how far apart are the published fits?
ina-sim rank --temp -20            # every measured material, heuristic layer off
ina-sim figures                    # 8 static reference plots, self-contained HTML
ina-sim freeze --id k_feldspar_harrison2019 --diameter 1 --curve
ina-sim validate                   # does this build still reproduce its sources?
ina-sim refs                       # the bibliography behind every number
```

### Bring your own experiment

`ina-sim assay` reads a cold-stage or microlitre-array run (CSV or JSON),
inverts it to an ns(T) spectrum with droplet-counting uncertainty (Wilson score
interval), flags the range your droplet count can actually resolve, and scores
it against every published fit on the same surface-area basis:

```
Against published fits on the same (BET) area basis:
parameterization                    n    bias   rmse  cover  verdict
k_feldspar_harrison2019            17   -0.07   0.14   100%  consistent with this fit
albite_harrison2019                17   +1.43   1.44     0%  sample is more active than this fit by >2 sigma
```

See [`docs/METHODS.md` §5](docs/METHODS.md) for the file format and
`examples/kfeldspar_synthetic_assay.csv` for a template.

## Rules the code enforces

- **No silent extrapolation.** Outside the range a source fitted, a parameterization returns nothing. `--extrapolate` overrides and stamps the result `EXTRAPOLATED`.
- **No mixing surface-area bases.** BET and geometric ns values differ by over an order of magnitude for clays, so ranking across bases raises `AreaBasisError`.
- **No unstated uncertainty.** A missing σ is replaced by a documented, attributed default and flagged `sigma_assumed`.
- **No unreferenced numbers.** Every coefficient names a key in `library/references.yaml`, and tests fail the build if one does not resolve.
- **No soluble salt scored as an ice nucleant.** NaCl, CaCl₂ and KI depress the freezing point; they get a colligative treatment and an explicit "no ns(T) exists".

## What this is not

- Not calibrated to any field campaign or seeding operation
- Not cloud-resolving, not radar verification
- Not operational seeding guidance, dosages or precipitation forecasts
- Not a substitute for a droplet-freezing assay — it predicts what one would measure
- Not complete: 8 parameterizations. `ina-sim rank` covers all of them; the heuristic `screen` covers the 8 library candidates, 4 of which have fits. No two fits describe the same material yet, so it cannot tell you where the literature disagrees. The gaps are visible on purpose

## Status (v0.3)

| Layer | State |
|-------|--------|
| **Empirical ns(T) / J(T) registry** | 7 published fits + 1 derived in-repo, with units, area basis, validity, σ, DOI |
| **Assay import** | your CSV/JSON run → ns(T) with Wilson bands, dynamic-range flags, comparison to published fits |
| **Polydisperse aerosol** | lognormal modes → INP concentration by exact integral (not ns × area), d50 of the particles carrying the ice nucleation, size truncation |
| **Intercomparison** | fits grouped by quantity + area basis; range across materials separated from genuine same-material conflict |
| **Empirical ranking** | `ina-sim rank` — every measured material ordered in log₁₀, no heuristic layer, no library entry needed |
| **Size and dose** | activation probability `1 − exp(−ns·πd²)` and INP concentration `N · P_act` — the particle-size and seeding-density inputs now change the answer |
| **Reference figures** | 8 static SVG plots built from the registry (`ina-sim figures`, or GUI ▸ Physics ▸ Reference figures) |
| **Droplet-freezing observables** | frozen fraction, Vali inversion, T50, INP concentration, cooling-ramp integration |
| **Singular + stochastic descriptions** | Vali (1971) and Murray et al. (2011), reported side by side |
| **Validation suite** | 5 anchors against published claims, run in CI (`ina-sim validate`) |
| **Solute physics** | colligative ΔTf, explicit "not an ice nucleant" |
| **L0/L1 + activity tables** | Working (CLI + GUI) |
| **Atmosphere** | Water + ice Magnus, S_w / S_i, RH_ice |
| **Tracks** | `ice` (glaciogenic) vs `warm_cloud` (CCN) |
| **Literature xref** | Directional public-research checks on every screen |
| **Provenance** | version, param_hash, assumptions, clamp report, evidence summary |
| **Molecular uploads** | SMILES/XYZ/MOL/JSON → exploratory builder feed |
| **GUI** | Win95 chrome, assumptions panel, mechanism banner |
| **CI** | pytest + ruff + mypy, plus a validation job that re-derives the anchors |
| **L2 MD / molecular builder** | Next |

```
Candidate library → track + conditions → activity tables / heuristics
  → rank + bands + sources
  → empirical layer: ns(T) with citation, or an explicit "nobody measured this"
  → literature_xref + validation + provenance export
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
ina-sim ns --temp -20
ina-sim assay examples/kfeldspar_synthetic_assay.csv
ina-sim validate
ina-sim gui                    # http://127.0.0.1:8765/
pytest -q
```

## Architecture pointer

```
src/ina_sim/
  units.py       SI conversions; the one place cm^-2 becomes m^-2
  references.py  bibliography loader (library/references.yaml)
  physics/       atmosphere, activity tables, efficiency, CNT, research_xref
                 ns.py        published parameterization registry + guards
                 freezing.py  frozen fraction, Vali inversion, T50, INP conc.
                 solutes.py   colligative freezing point depression
                 evidence.py  measured / solute / none, per candidate
  library/       candidates.yaml, activity_curves.yaml,
                 parameterizations.yaml, references.yaml
                 aerosol.py   lognormal modes, Hatch-Choate, INP integral
                 intercompare.py  grouping + spread vs real disagreement
                 dose.py      activation probability, INP concentration
  figures/       svg.py (stdlib plotting) + reference.py + page.py
  assay/         ingest.py (CSV/JSON + 3 surface-area routes)
                 spectrum.py  Vali inversion, Wilson bands, registry comparison
  validation/    anchors.yaml + runner (ina-sim validate)
                 datasets/ digitized literature measurements
  screen/        rank + uncertainty
  gui/           offline stdlib server + Win95 HTML
examples/        kfeldspar_synthetic_assay.csv (labelled synthetic template)
tools/           fit_agi_ns.py (derives the AgI fit), gen_docs.py,
                 make_example_assay.py
docs/            METHODS.md, VALIDATION.md, REFERENCES.md, PROJECT.md
tests/           376 tests: units, registry, freezing physics, assay import,
                 aerosol, intercomparison, dose,
                 figures, validation, references
```

## License

MIT — see [LICENSE](LICENSE). Scientific disclaimer: [CONTRIBUTING.md](CONTRIBUTING.md).

# Architecture

## Fidelity ladder

| Level | Role | v0.1 |
|-------|------|------|
| **L0** | Descriptors (lattice match, density, tags) | Partial (YAML fields) |
| **L1** | Heuristic efficiency + vapor inventory + rank | **Implemented** (mode/class pathways) |
| **L1b** | CNT-style free-energy barrier estimates | **Educational implemented** (`physics/cnt.py`) |
| **Atmosphere** | Water/ice Magnus, S_w, S_i, RH_ice, dewpoint | **Implemented** |
| **Research xref** | Directional public-literature consistency | **Implemented** (`physics/research_xref.py`) |
| **Uploads** | SMILES/XYZ/MOL → exploratory candidates | **Implemented** (builder feed) |
| **Empirical** | Published ns(T) / J(T) with units, basis, validity, σ, DOI | **Implemented** (`physics/ns.py`, `library/parameterizations.yaml`) |
| **Observables** | Frozen fraction, Vali inversion, T50, INP concentration | **Implemented** (`physics/freezing.py`) |
| **Validation** | Anchors against published claims, run in CI | **Implemented** (`validation/`) |
| **L2** | MD / seeding templates (OpenMM/GROMACS, CPU) | Planned |
| **Bridge** | Particle assumptions → INA/kg proxy | **Implemented (relative)** |

See **`docs/PROJECT.md`** for the full living handbook and
**`docs/METHODS.md`** for every equation with its source.

## Data flow

```
candidates.yaml ──► Candidate
                         │
Conditions ──────────────┤
                         ▼
              agent_efficiency()     total_water_vapor_kg()
                         │                      │
                         └──────────┬───────────┘
                                    ▼
                              ScreenResult ◄──── evidence_for()
                                    │                  │
                    rank + confidence + warnings       │
                                                       ▼
                                    parameterizations.yaml ─► ns.evaluate()
                                             │                     │
                                    validity + area basis     freezing.py
                                        guards                (f, T50, n_INP)
```

The two paths never merge. `agent_efficiency` produces the ranking score;
`evidence_for` reports what is measured, or states plainly that nothing is.
A candidate with no parameterization gets no invented number.

## Local compute notes

- Target machine: AMD Ryzen AI 7 PRO 350, ~28 GB RAM, **no NVIDIA** (AMD iGPU).
- Prefer CPU OpenMM/GROMACS when L2 lands; no CUDA dependency in core.

## Extending

1. **New mineral/molecule:** add YAML entry in `library/candidates.yaml` (demote confidence if unvalidated).
2. **New physics backend:** implement behind `screen/` without breaking `ScreenResult` schema.
3. **Experiment files:** write YAML under `experiments/` (convention TBD) and load via future CLI.
4. **New parameterization:** add a row to `library/parameterizations.yaml` and a
   reference to `library/references.yaml`. Required: `form`, `coefficients`,
   `ns_units`, `area_basis`, `t_min_c`, `t_max_c`, `reference`, and either the
   source's `quote` (published) or a `derivation` script and `dataset`
   (derived). Then add at least one anchor to `validation/anchors.yaml` that is
   independent of the coefficients — a claim in the paper's prose, an ordering
   it asserts, or a regime it must land in. Tests enforce all of this; a
   parameterization with no citation or no quote fails the build.
5. **After any of the above:** run `python tools/gen_docs.py` so
   `docs/VALIDATION.md` and `docs/REFERENCES.md` match the registry. CI checks.

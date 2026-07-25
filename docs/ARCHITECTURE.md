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
| **L2** | MD / seeding templates (OpenMM/GROMACS, CPU) | Planned |
| **Bridge** | Particle assumptions → INA/kg proxy | **Implemented (relative)** |

See **`docs/PROJECT.md`** for the full living handbook.

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
                              ScreenResult
                                    │
                    rank + confidence + warnings
```

## Local compute notes

- Target machine: AMD Ryzen AI 7 PRO 350, ~28 GB RAM, **no NVIDIA** (AMD iGPU).
- Prefer CPU OpenMM/GROMACS when L2 lands; no CUDA dependency in core.

## Extending

1. **New mineral/molecule:** add YAML entry in `library/candidates.yaml` (demote confidence if unvalidated).
2. **New physics backend:** implement behind `screen/` without breaking `ScreenResult` schema.
3. **Experiment files:** write YAML under `experiments/` (convention TBD) and load via future CLI.

# Architecture

## Fidelity ladder

| Level | Role | v0.1 |
|-------|------|------|
| **L0** | Descriptors (lattice match, density, tags) | Partial (YAML fields) |
| **L1** | Heuristic efficiency + vapor inventory + rank | **Implemented** |
| **L1b** | CNT-style free-energy barrier estimates | Planned |
| **L2** | MD / seeding templates (OpenMM/GROMACS, CPU) | Planned |
| **Bridge** | Particle assumptions → INA/kg proxy | **Implemented (relative)** |

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

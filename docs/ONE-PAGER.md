# INA-sim — one pager

## Mission

Local **ice-nucleating agent (INA) screening lab** for Rainmaker-track atmospheric fluency.  
**60% learning lab · 40% portfolio.** Not for sale. Not operational weather control.

## What it does

- Ranks candidate agents under T, RH, P, mode, and **track** (ice vs warm-cloud)  
- Table-driven activity vs T for key agents (directional literature flavor)  
- Educational CNT secondary scores  
- Literature cross-reference (pass/fail direction checks)  
- Molecular uploads (SMILES/XYZ/MOL) as **exploratory** builder feed  
- Explicit assumptions, provenance hash, uncertainty bands  

## Assumptions (always)

| Assumption | Default |
|------------|---------|
| Particle model | Monodisperse spheres |
| Diameter | 1 µm (user-settable) |
| Active-site fraction | 0.01 |
| relINA reference | η / 0.85 (AgI-class) |
| Fidelity | L0 + L1 activity tables + educational CNT |

## Limitations

- **Not** measured \(n_s(T)\) or field INP  
- **Not** cloud-resolving or radar-verified  
- Hygroscopic ≠ ice nucleant (separate track)  
- Uploads use placeholder efficiencies  
- Wet-lab required before any payload spend  

## Preferred delivery concept (personal)

Drone aerosolizer of relatively inert mineral / AgI-class agents.  
Ground generators out; flares out (carcinogens) at this stage.

## Stack

Python 3.11+, PyYAML, stdlib HTTP GUI, pytest CI.

## Repo docs

- Living handbook: `docs/PROJECT.md`  
- Professional checklist: `docs/PROFESSIONAL-ROADMAP.md`  
- Literature: `docs/LITERATURE-CHECKS.md`  

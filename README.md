# INA-sim

**Local multi-fidelity ice nucleation agent (INA) screening lab** for atmospheric weather-modification R&D (Rainmaker-track familiarity, alternative INA exploration, honest confidence scores).

> Decision-support lab — not operational weather control, not absolute nucleation rates.

```
Candidate library → conditions grid → L0/L1 heuristic screen → rank + INA/kg proxy + confidence
                                      (L2 MD deep-dives: planned)
```

## Status (v0.1)

| Layer | State |
|-------|--------|
| **L0/L1 heuristic screen** | Working (CLI) |
| **Candidate library** | AgI, minerals, hygroscopics, controls, exploratory organic |
| **INA/kg proxy** | Assumption-based relative figure of merit |
| **L2 MD** | Scaffold only (not implemented) |
| **Dashboard** | Not yet |

Physics for vapor inventory + agent efficiency curves was **cannibalized** from [`HearnChristian/supercool-water-calculator`](https://github.com/HearnChristian/supercool-water-calculator) (see `legacy/` and `src/ina_sim/physics/`).

## Quick start

```bash
cd ina-sim
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

ina-sim list
ina-sim screen --temp -10
ina-sim screen --temp -7 --ids agi k_feldspar kaolinite water_control
ina-sim show agi --temp -7
ina-sim screen --temp -15 --json --out data/results/screen.json
pytest
```

## Example

```text
$ ina-sim screen --temp -7
INA-sim screen @ T=-7.0°C  RH=95.0%  P=850.0 hPa  mode=immersion
rank  id              η   relINA   INA/kg*  conf          name
...
```

## Architecture

```
src/ina_sim/
  physics/     atmosphere (Magnus, density, vapor) + efficiency heuristics
  library/     YAML candidate pack
  bridge/      efficiency → relative INA / INA-per-kg proxy
  screen/      rank + screen_one
  models/      Candidate, Conditions, ScreenResult
  cli.py       list | screen | show
docs/          mission lock + voice-note prompts
legacy/        original supercool-water-calculator snapshot
```

## Confidence tiers

| Tier | Meaning |
|------|---------|
| **high** | Baseline class with expected directional behavior |
| **medium** | Plausible physics, limited validation |
| **low** | Weak parameterization |
| **exploratory** | Novel organics / unvalidated — **never for payload claims** |

## Honest limitations

- Hygroscopic seeders (NaCl, CaCl₂) ≠ ice nucleants (AgI, feldspar); shared ranking UX only.
- Efficiency model is a **demo heuristic** (legacy exp-temp falloff), not classical nucleation theory.
- `ina_per_kg_proxy` assumes monodisperse spheres + fixed active-site fraction — change assumptions before any sales narrative.
- No MD, no cloud-resolving model, no operational guidance.

## Mission

Primary: atmospheric weather modification / Rainmaker Tech Corp skill-building.  
Secondary: ice-promoting organics (exploratory).  
Out of scope for now: general materials discovery lab.

See `docs/INA-sim-mvp.md`.

## License

MIT — see [LICENSE](LICENSE).

## Provenance

- SuperCool Liquid Water Calculator logic → `src/ina_sim/physics/` + agent table seeds  
- Snapshot preserved under `legacy/supercool-water-calculator/`

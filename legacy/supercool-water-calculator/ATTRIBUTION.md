# supercool-water-calculator (legacy snapshot)

**Source:** https://github.com/HearnChristian/supercool-water-calculator  
**Role in INA-sim:** seed physics + agent table for L0/L1 heuristics.

## What was reused

| Legacy (JS in index.html) | INA-sim home |
|---------------------------|--------------|
| Magnus sat. vapor pressure | `physics/atmosphere.py::saturating_vapor_pressure_hpa` |
| Specific humidity | `physics/atmosphere.py::specific_humidity` |
| Ideal-gas air density | `physics/atmosphere.py::air_density_kg_m3` |
| Cloud vapor inventory | `physics/atmosphere.py::total_water_vapor_kg` |
| Temp / density efficiency factors | `physics/efficiency.py` |
| Condensable water product | `physics/efficiency.py::condensable_water_kg` |
| Agents AgI, NaCl, CaCl₂, KI, TEST | `library/candidates.yaml` |

## What was *not* blindly trusted

- Treating all agents as interchangeable “seeders” (INA-sim splits ice_nucleant / hygroscopic / organic / control).
- Absolute precipitation volume claims without uncertainty.
- Testosterone as a serious operational agent (kept as **exploratory** only).

Files here are an archival copy for provenance; the maintained code lives under `src/`.

#!/usr/bin/env python3
"""Generate the SYNTHETIC example droplet-freezing file.

There is no real cold-stage run in this repo to ship as an example, and
inventing one and presenting it as data would be exactly the sin the rest of
INA-sim is built to avoid. So this script writes an openly synthetic file: it
takes the published K-feldspar fit, simulates 100 droplets freezing under it,
and labels the result as simulated in the file's own header.

That makes the example useful for two things and no others:

  1. showing the shape a real file should take;
  2. a round-trip test - importing it must recover the fit it came from, which
     exercises the whole path from CSV to ns(T) to comparison.

Each droplet gets a uniform random number and freezes at the first temperature
where the modelled frozen fraction exceeds it, which reproduces exactly the
binomial statistics a real assay has and keeps the cumulative count monotone.

Usage:
    python tools/make_example_assay.py
"""

from __future__ import annotations

import random
from pathlib import Path

from ina_sim.physics.freezing import frozen_fraction_singular
from ina_sim.physics.ns import evaluate, get_parameterization

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "examples" / "kfeldspar_synthetic_assay.csv"

PARAM_ID = "k_feldspar_harrison2019"
SEED = 20260725
N_DROPLETS = 100

# A plausible cold-stage recipe: 0.05 g/L suspension, 1 uL droplets, BET
# specific surface area 3 m2/g -> 1.5e-7 m2 of mineral per droplet.
CONCENTRATION_G_PER_L = 0.05
DROPLET_VOLUME_UL = 1.0
SPECIFIC_SURFACE_AREA_M2_PER_G = 3.0
COOLING_RATE_K_PER_MIN = 1.0

T_START_C = -5.0
T_END_C = -20.0
T_STEP_C = 0.5


def main() -> int:
    param = get_parameterization(PARAM_ID)
    area_m2 = (
        CONCENTRATION_G_PER_L * DROPLET_VOLUME_UL * 1e-6 * SPECIFIC_SURFACE_AREA_M2_PER_G
    )

    rng = random.Random(SEED)
    thresholds = sorted(rng.random() for _ in range(N_DROPLETS))

    n_steps = int(round((T_START_C - T_END_C) / T_STEP_C))
    rows: list[tuple[float, int]] = []
    for i in range(n_steps + 1):
        temp = T_START_C - i * T_STEP_C
        est = evaluate(param, temp)
        expected = (
            0.0 if est.value is None else frozen_fraction_singular(est.value, area_m2)
        )
        frozen = sum(1 for t in thresholds if t <= expected)
        rows.append((temp, frozen))

    lines = [
        "# SYNTHETIC DATA - NOT A MEASUREMENT.",
        f"# Simulated by tools/make_example_assay.py (seed {SEED}) from the",
        f"# {PARAM_ID} fit, to demonstrate the file format and to round-trip",
        "# test the importer. Do not cite these numbers as an experiment.",
        "#",
        "# material: K-feldspar (simulated)",
        "# sample: synthetic-kga-demo",
        "# area_basis: BET",
        f"# concentration_g_per_l: {CONCENTRATION_G_PER_L}",
        f"# droplet_volume_ul: {DROPLET_VOLUME_UL}",
        f"# specific_surface_area_m2_per_g: {SPECIFIC_SURFACE_AREA_M2_PER_G}",
        f"# cooling_rate_k_per_min: {COOLING_RATE_K_PER_MIN}",
        "# counting: cumulative",
        f"# notes: {N_DROPLETS} droplets simulated under Harrison et al. (2019)",
        "temperature_c,n_frozen,n_total",
    ]
    for temp, frozen in rows:
        lines.append(f"{temp:g},{frozen},{N_DROPLETS}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO_ROOT)}  ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

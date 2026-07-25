# Literature / known-data checks

INA-sim is a **learning lab**, not a calibrated INP model. Automated checks live in:

- `tests/test_literature.py` — atmosphere + ranking direction  
- `tests/test_research_xref.py` — public-research cross-reference block  
- `src/ina_sim/physics/research_xref.py` — runtime `literature_xref` on `/api/screen`  

**Rule:** if a ranking change inverts a known scientific direction, **fix the model** or update this doc with a cited reason — do not silence checks quietly.

---

## Atmosphere (Magnus)

| Check | Expected | Public research flavor |
|-------|----------|------------------------|
| \(e_{s,w}(0\,°C)\) | ≈ 6.11 hPa (±2%) | Handbook / IAPWS neighborhood; August–Roche–Magnus / Alduchov–Eskridge family |
| \(e_{s,w}(-10\,°C)\) | ~2.3–3.0 hPa | Magnus family |
| \(T<0\): \(e_{s,i} < e_{s,w}\) | True | Supercooled liquid metastable relative to ice |
| Fixed vapor, \(T<0\): \(RH_i > RH_w\) | True | \(RH_i = e/e_{s,i}\); mixed-phase / Bergeron context |
| High RH, cold: \(S_i > 1\) possible | True | Deposition / ice growth context |
| \(RH=100\%\): dewpoint ≈ T | Within ~0.15 °C | Inverse Magnus |

**Not claimed:** WMO operational Goff–Gratch accuracy over full climate range.

---

## Classical nucleation (educational)

| Check | Expected |
|-------|----------|
| \(S ≤ 1\) | Barrier undefined (`valid=False`) |
| Higher lattice match | Lower \(f(m)\), lower \(\Delta G^*_{het}\) |
| \(f(m=1)\approx 0\), \(f(m=-1)=1\) | Classic spherical-cap geometric factor |

**Not claimed:** Absolute \(J\) matches any cloud-chamber experiment.

---

## Ice-nucleating agents (directional)

| Check | Expected | Public research flavor |
|-------|----------|------------------------|
| AgI ≫ water control / inert | Mixed-phase immersion | Classic glaciogenic seeding agent (Vonnegut-era lineage; seeding reviews) |
| AgI competitive at −15…−5 °C | Not bottom-ranked | Operational cold-cloud seeding window (teaching scale) |
| K-feldspar > kaolinite | −25…−5 °C immersion | Atkinson et al., *Nature* 2013 — K-feldspar as key mineral-dust ice nucleant; clay comparisons (e.g. Zolles et al.) |
| NaCl not top ice agent when cold | AgI, feldspar above NaCl at ≤−10 °C immersion | Sea salt primarily **CCN** / hygroscopic, not leading atmospheric INA |
| AgI weaker far from \(T_{opt}\) | η(−7) > η(−35) | Library \(T_{opt}=-7\) °C + falloff |
| Deposition needs ice supersat | Higher η at high RH_ice | Deposition freezing physics |
| Hygroscopic pathway labeled | Separate from ice_nucleation | Mechanism distinction in aerosol–cloud science |

### Homogeneous freezing

Pure-water homogeneous freezing of small droplets is typically near **−35…−38 °C** (Pruppacher & Klett / standard cloud physics).  
`water_control` is a **weak control**, not a full stochastic homogeneous model — must stay far below AgI in mixed-phase.

### Not in starter set (known, deferred)

| Agent class | Note |
|-------------|------|
| Snomax / *P. syringae* | Extremely efficient biological INA (~−2…−7 °C class) — open for later |
| Lead iodide | Historical toxic contrast — academic only if ever added |

---

## Runtime `literature_xref`

Every successful `/api/screen` (and `run_screen_payload`) returns:

```json
"literature_xref": {
  "summary": {"pass": N, "fail": 0, "skip": M, "ok": true},
  "checks": [{"id": "...", "status": "pass|fail|skip", "detail": "...", "refs": "..."}],
  "disclaimer": "Directional ... not calibration to ns(T)"
}
```

GUI shows a one-line summary under the results table (hover for full check list).

---

## How to re-run

```bash
cd ~/ina-sim && source .venv/bin/activate
pytest tests/test_literature.py tests/test_research_xref.py -q
pytest -q
```

## When a check fails

1. YAML `base_efficiency` / `optimal_temp_c` change?  
2. Mode/class pathway weights inverted mineral order?  
3. Intentional science change? → update this file + `research_xref.py` with reason.  

Also update `docs/PROJECT.md` §6 / §8 / §13.

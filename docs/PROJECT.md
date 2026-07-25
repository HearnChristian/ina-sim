# INA-sim — Project handbook (living doc)

**Last updated:** 2026-07-24 (v0.2 professional upgrade)  
**Maintainer rule:** When you change mission, physics, GUI behavior, APIs, or library ranking intent, update **this file** in the same change.  
**Skill:** `.grok/skills/ina-sim/SKILL.md` (auto-loaded for INA-sim work)  
**Professional checklist:** `docs/PROFESSIONAL-ROADMAP.md` (all review suggestions recorded + status)

---

## 1. What this is

| | |
|--|--|
| **Name** | INA-sim |
| **Path** | `~/ina-sim` |
| **Split** | **60% learning lab · 40% portfolio** |
| **Not** | A product to sell, operational weather control, or lab-calibrated INP model |
| **Why** | Rainmaker-track atmospheric fluency; rank ice-nucleating agents (INAs) under honest confidence |
| **Mission lock** | `docs/REFLECTION-LOCK-2026-07-24.md`, `docs/INA-sim-mvp.md` |

### Success bar

1. Numbers mean physics-validated **ranges** (not fake precision)  
2. Can explain AgI, feldspar, dust, immersion vs deposition, what the sim does **not** prove  
3. 10-minute demo: conditions → rank table → sketch  
4. Optional: novel molecule upload for future molecular builder  

---

## 2. Quick commands

```bash
cd ~/ina-sim
source .venv/bin/activate
pip install -e ".[dev]"

ina-sim list
ina-sim screen --temp -10 --tag starter-set
ina-sim screen --temp 0 --track warm_cloud
ina-sim gui                    # http://127.0.0.1:8765/
ina-sim gui --no-browser
ina-sim upload --smiles CCO --name Ethanol
ina-sim uploads
pytest -q
pytest tests/test_literature.py tests/test_research_xref.py tests/test_golden.py -q
```

If GUI dies: process was killed (exit 137) or port conflict — restart with `ina-sim gui`. Hard-refresh browser (`Ctrl+Shift+R`).

---

## 3. Architecture (current)

```
src/ina_sim/
  physics/
    atmosphere.py   # Magnus water/ice, S_w, S_i, RH_ice, dewpoint, vapor mass
    activity.py     # table-driven relative activity vs T
    cnt.py          # educational CNT (ΔG*, r*, f(m), scores)
    efficiency.py   # L1 η: activity × density × mode × track/class (+ light CNT)
    research_xref.py# public-research directional checks on rankings
    validate.py     # clamps / finite guards / lab envelope
  library/
    candidates.yaml # packaged agents (no curiosity organics by default)
    activity_curves.yaml
    molecular.py / registry.py  # builder feed uploads
  provenance.py / schema.py
  screen/rank.py
  gui/
docs/  PROJECT.md, PROFESSIONAL-ROADMAP.md, ONE-PAGER.md, DEMO-SCRIPT.md
tests/ golden fixtures, properties, literature, stress
```

### Fidelity ladder

| Level | Role | State |
|-------|------|--------|
| L0 | Descriptors (lattice, density, tags) | Partial |
| L1 | Activity tables + heuristics + vapor inventory | **Implemented** |
| L1b | Educational CNT (secondary only) | Implemented |
| Tracks | `ice` vs `warm_cloud` | Implemented |
| Research xref | Directional literature consistency | Implemented |
| Provenance | param_hash, assumptions, clamp report | Implemented |
| L2 | MD (OpenMM/GROMACS) | Not started |
| Molecular builder | Structure → better descriptors | **Next project** |

---

## 4. GUI behavior (locked UX)

| Control | Behavior |
|---------|----------|
| **Sliders** | Drag updates **labels only** |
| **Run Screen** | Applies current conditions (primary action); controls disabled while in flight |
| **Live on release** | **Off by default.** If on: runs only on **release**, never mid-drag |
| **Results** | Fingerprint + **stale** state; relINA **bands**; **source** column |
| **Assumptions** | Always-visible panel (diameter, hash, clamp) |
| **Track banner** | Ice vs warm-cloud mechanism banner |
| **Export JSON** | File menu only (includes provenance) |
| **Upload** | **Physics → Upload molecule…** (not on main chrome) |
| **Core agents only** | Limits table to 5 demo agents (was “starter set”) |
| **Tips** | **View → Cursor tips** toggle (off by default; labels stay plain English) |
| **Rank for** | Ice nucleants (INA) vs liquid drops (CCN) — glossary under Physics/Help |
| **Sketch** | Larger chart with axes; score bars + sparse ice marks |
| **Menus** | File / View / Physics / Help are real dropdowns |

**Why not live-on-drag:** concurrent aborts produced inconsistent ranks (stale responses vs mid-drag T). Determinism > flashiness.

---

## 5. Screening model (honest summary)

\[
\eta \approx \eta_0 \cdot f_T(T) \cdot f_{\mathrm{mode}} \cdot f_{\mathrm{class}} \cdot f_{\mathrm{density}}
\]

- Ice nucleants: small CNT score blend  
- Density multiplies last (zero loading → zero activity)  
- `relINA = η / 0.85` (AgI-class reference)  
- Hygroscopics (NaCl, CaCl₂) are **not** ice nucleants — pathway labeled `hygroscopic_ccn`  

Uploads get **placeholder** η and always exploratory confidence.

**This is the ranking layer, and it is a convention, not a measurement.** Since
v0.3.0 a second, separate layer answers the harder question — what has anybody
actually measured? See `docs/METHODS.md`:

\[
n_s(T)\ \text{[m}^{-2}\text{]}, \quad f = 1 - e^{-n_s A}, \quad
n_s = \frac{-\ln(1-f)}{A}\ \text{(Vali 1971)}
\]

- 8 parameterizations in `library/parameterizations.yaml`, each with units,
  surface-area basis, validity range, sigma and DOI
- outside a source's fitted range the tool returns **nothing**, not an
  extrapolation
- BET and geometric ns values are never ranked against each other
- soluble salts (NaCl, CaCl2, KI) get colligative freezing-point depression and
  an explicit "no ns(T) exists" — KI was reclassified out of `ice_nucleant`
- `ina-sim validate` re-derives 5 literature anchors on every CI run

---

## 6. Starter library (intent)

| ID | Role | Literature intent |
|----|------|-------------------|
| `agi` | Baseline glaciogenic | Classic seeding agent; mixed-phase cold clouds |
| `k_feldspar` | Strong mineral INA | Often warmer / more active than clays (Atkinson et al.) |
| `kaolinite` | Weaker clay | Typically colder / lower activity than feldspar |
| `water_control` | Negative | Homogeneous ~−35…−38 °C class |
| `nacl` | CCN contrast | Soluble salt, no ns(T); depresses freezing |
| `ki` | Soluble salt | Reclassified v0.3.0 — was wrongly an `ice_nucleant` |

Measured coverage: `agi`, `k_feldspar`, `kaolinite` and `water_control` have a
parameterization; the rest are heuristic only, and every screen says so.

See `docs/LITERATURE-CHECKS.md` and `physics/research_xref.py`.

---

## 7. APIs (local only)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Offline health + upload count |
| GET | `/api/screen?...` | Rank + atmosphere + literature_xref |
| GET | `/api/tsweep?...` | Temperature map |
| GET | `/api/uploads` | Session uploads |
| POST | `/api/upload/molecule` | Molecular ingest |
| DELETE | `/api/uploads/<id>` | Remove upload |

No external network required at runtime.

---

## 8. Public research cross-reference

Screen payloads include `literature_xref`: pass/fail/skip checks against **directional** public knowledge (not absolute rates).

Key anchors (see also literature doc):

- \(e_{s,w}(0°C) ≈ 6.11\) hPa  
- \(T<0\): \(e_{s,\mathrm{ice}} < e_{s,w}\); \(RH_i > RH_w\) at fixed vapor  
- Homogeneous freezing pure water droplets ~ **−35…−38 °C**  
- **AgI** effective glaciogenic in cold mixed-phase (historical seeding literature)  
- **K-feldspar** dominant mineral dust ice nucleant (Atkinson et al., Nature 2013 lineage)  
- **Kaolinite** less active / colder than K-feldspar in immersion studies  
- **Sea salt** primarily CCN, not competitive INA at −15 °C immersion  

**Never claim:** match to measured \(n_s(T)\), radar verification, or operational seeding doses.

---

## 9. Delivery opinions (from reflection)

| Mode | Verdict |
|------|---------|
| Ground generators | Out (no proof) |
| Flares / pyrotechnic | Out this stage (carcinogens) |
| Drone aerosolizer | Preferred mental model |
| Agent pick order | Environment/optics → price → performance (higher-T rain interest) |

---

## 10. Time budget

- ~1 h/day active  
- Overnight batch/ML OK  
- Open source; post if it works  

---

## 11. Next projects

1. **Molecular builder** — structure UI → real descriptors → replace placeholder η  
2. Learning notes (CNT, seeding practice, chambers, hygroscopy, operator metrics)  
3. Pixel nucleation viz polish  
4. Higher-T / warm-cloud research track  
5. L2 MD template (CPU OpenMM)  
6. Atmos radar coupling (long term)  

---

## 12. Doc index

| File | Role |
|------|------|
| **`docs/PROJECT.md`** | **This handbook — keep current** |
| `docs/REFLECTION-LOCK-2026-07-24.md` | Voice reflection decisions |
| `docs/INA-sim-mvp.md` | Mission lock summary |
| `docs/LITERATURE-CHECKS.md` | Testable literature anchors |
| `docs/ARCHITECTURE.md` | Fidelity ladder sketch |
| **`docs/METHODS.md`** | **Every equation, unit, source and enforced rule** |
| `docs/VALIDATION.md` | Generated: anchors this build reproduces |
| `docs/REFERENCES.md` | Generated: bibliography with DOIs and usage |
| `docs/voice-note-prompts.md` | Historical free-association prompts |
| `README.md` | Install + quick start |

---

## 13. Changelog (project handbook)

| Date | Note |
|------|------|
| 2026-07-25 | **v0.3.5** `ina-sim uncertainty`: Monte Carlo n_INP with log-normal ns, normal temperature and log-normal aerosol error → percentiles, P(above threshold), and a variance decomposition (frozen-input, common random numbers) naming which input owns the spread. For the standard dust case ns(T) is 96% of it, i.e. a better instrument would not help. Deterministic per seed; out-of-range draws discarded and reported, never extrapolated. 9th reference figure: the exceedance curve |
| 2026-07-25 | **v0.3.4** Made the inert controls matter: particle diameter now acts through P_act = 1 − exp(−ns·πd²) (measured ns where one exists, otherwise the score read as activation at a 1 µm reference, exact there so nothing already working moved), and seeding density drives an uncapped n_INP. Pressure and immersion-mode humidity stay inert on purpose, with a test pinning that. New `ina-sim figures` / GUI ▸ Physics ▸ Reference figures: 8 static SVG plots generated from the registry, offline, no scripts |
| 2026-07-25 | **v0.3.3** `ina-sim rank`: empirical-only screening in log10, covering all 8 parameterizations rather than the 4 with library entries. Documented why quartz/plagioclase/albite/dust are NOT forced into the heuristic score (a 10-decade quantity on a linear 0–1 axis makes real minerals look inert) and what the three remaining gaps actually are |
| 2026-07-25 | **v0.3.2** `ina-sim aerosol`: lognormal size distributions → INP concentration via the exact activation integral (not ns × S_tot), d50 of the particles carrying the nucleation, instrument-range truncation. `ina-sim compare`: fits grouped by quantity + area basis, with 'range across materials' separated from genuine same-material conflict (material_key added to every parameterization; this build has zero same-material pairs and says so) |
| 2026-07-25 | **v0.3.1** `ina-sim assay`: import a real droplet-freezing run (CSV/JSON, 3 surface-area routes) → ns(T) with Wilson counting bands, one-sided limits at f=0/1, dynamic-range flags, and scored comparison against every fit on the same area basis; synthetic example + round-trip test |
| 2026-07-25 | **v0.3.0** Empirical layer: published ns(T)/J(T) registry with DOIs, units and validity guards; Vali inversion + T50 + INP concentration; stochastic (Murray 2011) freezing; derived AgI fit from Marcolli 2016 Table 1 (sigma 1.8 decades, honestly reported); validation anchors in CI; KI reclassified as a soluble salt; 248 tests; mypy clean |
| 2026-07-24 | **v0.2.1** Score scale fixed 0–1 (AgI peak=1); plotters+axes; T-sweep X label; empirical_claims extraction |
| 2026-07-24 | UI refine: upload→Physics menu; Core agents only; tip toggle; INA/CCN plain language; larger sketch + axes |
| 2026-07-24 | **v0.2** Professional upgrade: activity tables, tracks, bands, provenance, golden CI, assumptions UI, roadmap, demo/one-pager, CONTRIBUTING |
| 2026-07-24 | Initial comprehensive handbook; slider UX locked; research_xref; project skill |
| 2026-07-24 | Reflection lock; Win95 GUI; CNT; molecular upload; offline hardening |

---

## 14. Agent maintenance checklist

When finishing a coding session on INA-sim:

1. [ ] Tests green (`pytest -q`)  
2. [ ] Update **§13 changelog** + any changed sections above  
3. [ ] If ranking/physics intent changed → `LITERATURE-CHECKS.md` + `research_xref.py`  
4. [ ] If GUI UX changed → §4  
5. [ ] If new API → §7  

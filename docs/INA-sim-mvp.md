# INA-sim MVP — Mission Lock

**Created:** 2026-07-22  
**Updated:** 2026-07-24 (voice reflection lock)  
**Status:** Requirements locked from reflection  
**Primary mission:** Atmospheric weather-mod literacy (Rainmaker track)  
**Authoritative reflection:** [`REFLECTION-LOCK-2026-07-24.md`](REFLECTION-LOCK-2026-07-24.md)

---

## One-line mission

Build a **local virtual lab** that ranks ice-nucleating agents under honest confidence scores — **60% personal learning lab, 40% portfolio** — so you can operate fluently in Rainmaker-relevant atmospheric physics and brainstorm alternative INAs. **Not a product to sell.**

---

## What is locked (2026-07-24 supersedes earlier defaults)

| Decision | Choice |
|----------|--------|
| **Primary use case** | Rainmaker-track atmospheric weather-mod familiarity |
| **Split** | 60% learning lab · 40% portfolio |
| **Not** | Profitable product / moat / sales-facing polish |
| **Product philosophy** | Decision-support + education: which agents, under which conditions, with what confidence — numbers must mean physics-validated **ranges** |
| **Compute** | Local only. ~1 h/day active; overnight ML/batch OK |
| **Success bar** | Fluency + honest rank table + simple graphic demo — *not* "sell payload to a company" |
| **Delivery preference** | Drone aerosolizer; ground gens out; flares out (carcinogens) |
| **Agent priority** | Optics/environment first → price/availability → performance (incl. higher-T rain interest) |
| **V1 conditions** | Supersaturated systems; immersion; no dirty-cloud/solute chemistry |
| **Open source** | Yes; post publicly if it works |

---

## Hardware (checked 2026-07-22)

### Primary: Linux ThinkPad (`CTH-ThinkPad`)

| Spec | Value | Implication |
|------|-------|-------------|
| CPU | AMD Ryzen AI 7 PRO 350 (8c/16t) | L0/L1 screens, batch, future CPU MD |
| RAM | ~28 GiB | Modest MD later |
| GPU | AMD Radeon 860M — **no NVIDIA** | No CUDA |
| OS | Ubuntu 24.04 | Science stack OK |

### Secondary: MacBook Air

Notes, light L0/L1, demos — not MD workhorse.

---

## Career / context

- Applied to **Rainmaker Tech Corp**; want fall–winter competence.  
- Complementary to Atmos / radar / hardware work — this is materials/microphysics fluency.  
- Karmic framing: rain-on-demand as high-upside planetology tech (personal motivation; not a product claim).

---

## Product shape

```
Candidate library
  → conditions (T, RH, P, supersat-leaning defaults)
  → L0/L1 heuristic screen (later: CNT, optional L2 MD)
  → rank table: INA | rel. effectiveness (vs AgI) | conf [| price later]
  → small graphic (pixel nucleation viz = stretch)
```

**Confidence tiers:** high / medium / low / exploratory — exploratory never for payload language.

---

## Starter candidates (locked start set)

| # | Agent | Role |
|---|-------|------|
| 1 | **AgI** | Baseline benchmark (cost is its main downside) |
| 2 | **K-feldspar** | Mineral INA |
| 3 | **Kaolinite** | Clay contrast |
| 4 | **Water / control** | Negative control |
| 5 | **Sea salt (NaCl)** | Keep; **assume weak INA** until convinced; CCN teaching case |

**Open later:** Snomax / biological, other minerals, fungal-spore / mycorrhizal *one-pager* (separate idea).  
**Hygroscopics (CaCl₂, etc.):** contrast only — mechanism ≠ ice nucleation; do not rank as if same class without warnings (already in code).

---

## MVP in / out

### In MVP

- Local CLI (+ minimal GUI: table + small image)  
- Library above + confidence badges  
- Relative effectiveness vs AgI  
- INA/kg **proxy** with explicit assumptions  
- Physics-honest ranges, not fake precision  
- Export table/JSON  

### Out of MVP

- Sales product polish  
- Ground generators / flares as recommended delivery  
- Dirty clouds, solutes, pollution chemistry  
- Geographic ops cases  
- Absolute rates matching every paper  
- Full protein INP / Snomax MD  
- CUDA-only pipelines  
- Operational readiness claims  

### Stretch

- Retro 32/64-bit nucleation relative-rate viz  
- Price-per-mass column (YAML when researched)  
- Higher-T rain effectiveness literature + model branch  
- Drone / artillery delivery assumption docs  
- L2 MD template  
- Radar / Atmos coupling  

---

## Success metrics (90-day, reflection-aligned)

| Goal | Done when |
|------|-----------|
| **Baselines behave** | AgI and minerals rank directionally sensibly vs control in expected T window |
| **Table** | INA list with rel. effectiveness + confidence under stated conditions |
| **Meaning** | Can explain every column + assumptions to a technical listener |
| **Demo (10 min)** | Cold start → screen → table + one graphic |
| **Fluency** | CNT basics, seeding practice, cloud chambers, hygroscopy, operator metrics — enough to not bluff |

Wet-lab still required for any real payload spend. Sim narrows and teaches.

---

## Build order (from reflection backlog)

1. Keep CLI screen solid; label **baseline = AgI** clearly  
2. Minimal GUI: results table + tiny graphic  
3. Learning notes (CNT, seeding, chambers, hygroscopy, operator metrics)  
4. Price field (optional data)  
5. Pixel nucleation viz  
6. Higher-T / warm-cloud research track  

---

## File map

| File | Role |
|------|------|
| `docs/REFLECTION-LOCK-2026-07-24.md` | Full locked decisions from voice note |
| `docs/INA-sim-mvp.md` | This summary |
| `docs/ARCHITECTURE.md` | Fidelity ladder + code layout |
| `docs/voice-note-prompts.md` | Original free-association guide (historical) |
| `src/ina_sim/` | Implementation |

---

## Conversation log (condensed)

1. Wanted full INA sim for alternative agents; multi-fidelity advice; mission A.  
2. Hardware checked; v0.1 CLI + library shipped from supercool calculator physics.  
3. **2026-07-24 reflection:** 60/40 learning/portfolio; not for sale; AgI/feldspar/kaolinite/water/sea-salt start set; drone aerosol preferred; flares/ground gens out; environment then price then performance; supersat V1; table + small graphic; ~1 h/day; open source; learning list locked. Success = fluency + honest numbers, not payload sales.

# INA-sim MVP — Mission Lock

**Created:** 2026-07-22  
**Status:** Requirements capture (pre–voice note)  
**Primary mission:** A — atmospheric weather modification (Rainmaker Tech Corp track)

---

## One-line mission

Build a **local virtual lab** that ranks ice-nucleating agents for weather-modification style use, with honest confidence scores — so I can develop familiarity for Rainmaker, explore ice-promoting organics as a stretch, and eventually argue payload viability (activity / kg) with a sexy, extensible sim.

---

## What I have decided

| Decision | Choice |
|----------|--------|
| **Primary use case** | A — atmospheric weather modification / Rainmaker familiarity |
| **Secondary** | Ice-promoting organics (huge if possible; not blocking MVP) |
| **Out of scope (for now)** | General materials discovery lab (1–2 steps too far) |
| **Product philosophy** | Decision-support lab: which candidates deserve wet-lab / payload attention, under which conditions, and *why* — not “the absolute truth about ice” |
| **Compute** | Local only (no servers). Linux ThinkPad primary; MacBook Air secondary |
| **Desired outputs (all)** | Ranked list, T maps, INA/kg proxy, MD-style deep dives, novel candidate intake, **confidence-of-confidence** scores |
| **Success bar** | Confidence to **buy/formulate a payload** and sell the story to a rainmaking company with a **viable amount/kg** claim that is *honestly* uncertainty-banded — plus a demo sim that looks serious |

---

## Hardware (checked 2026-07-22)

### Primary: Linux ThinkPad (`CTH-ThinkPad`)

| Spec | Value | Implication for INA-sim |
|------|-------|-------------------------|
| CPU | AMD Ryzen AI 7 PRO 350 (8c/16t, up to ~5.1 GHz) | Strong for L0/L1 screens, batch jobs, OpenMM CPU |
| RAM | ~28 GiB | Comfortable for modest MD boxes; watch trajectory bloat |
| GPU | AMD Radeon 860M (iGPU) — **no NVIDIA** | No CUDA. Prefer CPU OpenMM/GROMACS; ROCm later if worth pain |
| Disk | ~913 GB root, ~741 GB free | Fine; still store analyses not full traj by default |
| OS | Ubuntu 24.04.4 LTS | Good science stack support |

### Secondary: MacBook Air

- Useful for notes, UI demos, light L0/L1, presentations to Rainmaker.
- Not the MD workhorse unless Apple Silicon + OpenMM Metal is intentionally set up later.
- Treat as **laptop B for polish and portability**, not primary physics.

**Compute reality check:** Overnight CPU MD for deep dives is feasible. Interactive brute-force nucleation for every candidate is not. Multi-fidelity (fast screen → optional deep dive) is mandatory.

---

## Career / context

- Applied to **Rainmaker Tech Corp**; hope to work with them **fall–winter**.
- This project is partly **skill + credibility building** for atmospheric weather modification.
- Also a **portfolio piece**: sexy sim + defensible ranking + payload narrative.
- Related local work already exists in atmos/hardware (Atmos PCB, atmos-sense, radar notes) — INA-sim is the *materials / microphysics* complementary thread, not a replacement for sensors/hardware.

---

## Product shape (locked enough to build)

```
Candidate in (mineral / molecule / library pick)
    → condition grid (T, mode, simple composition)
    → fidelity router (L0 descriptors → L1 rate proxy → optional L2 MD)
    → rank + T window + INA/kg proxy + confidence badge
    → export / demo view
```

**Confidence-of-confidence:** every result carries a tier, e.g.:

| Tier | Meaning |
|------|---------|
| **High** | Validated class + baseline match + method appropriate |
| **Medium** | Plausible physics, limited validation for this class |
| **Low / exploratory** | Novel organic or unparameterized system; rank only, not sell |

Payload sales language only rides on **High** (and carefully on **Medium** with caveats). Sexy sim can still show Low for exploration.

---

## Proposed starter candidates (for reflection — not final)

### Tier 1 — must have baselines (weather mod credibility)

1. **Silver iodide (AgI)** — industry classic; lattice-match story; always-on benchmark  
2. **Potassium feldspar (K-feldspar)** — strong natural mineral INA; dust-relevant  
3. **Kaolinite** — well-studied clay; often weaker/more nuanced than feldspar  
4. **Pure water / inert control** — homogeneous or non-nucleating surface (negative control)  

### Tier 2 — weather-mod adjacent / “what companies care about”

5. **NaCl / sea-salt proxy** — contrast; often *not* a great INA (good teaching case)  
6. **Snomax / bacterial protein proxy (later)** — biological INA; famous extreme case; defer full protein MD  
7. **Lead iodide (historical)** — literature contrast to AgI (careful: toxicity; academic only)  
8. **Graphite / soot proxy** — mixed/complex atmospheric relevance; lower confidence  

### Tier 3 — ice-promoting organics (secondary stretch)

9. **Simple ice-binding motifs / alcohols or polyols (e.g. related literature)** — teach H-bond effects  
10. **Long-chain alcohols / monolayers (if literature-backed)** — known ice-nucleating organics at interfaces  
11. **User-defined novel small molecule** (SMILES) — demo “add anything,” flagged exploratory  
12. **Testosterone (optional curiosity)** — only as *exploratory organic*, never as payload claim  

**Recommendation for v1 library:** ship **1–4 always**, add **5**, stub **9–11** for the sexy “novel intake” path. Defer proteins and toxic historical agents until after Rainmaker-relevant minerals work.

---

## MVP in / out (refined for Rainmaker track)

### In MVP

- Local CLI + simple dashboard  
- Candidate library (AgI, feldspar, kaolinite, control + 1–2 organics stubs)  
- Add novel mineral/molecule entry (with auto confidence demotion)  
- Condition grid: temperature focus; immersion-mode first; optional simple RH/solute flag  
- L0 descriptors + L1 ranking / T-band estimates  
- INA per kg **proxy** with **explicit assumptions** (size, SSA, active fraction)  
- Confidence badges + provenance (params, model version, seed)  
- Compare-to-AgI always available  
- Export table/report for demo  

### Out of MVP (explicit)

- Full cloud-resolving / weather-model coupling  
- Absolute nucleation rates matching every paper  
- Production protein INP simulation  
- General materials discovery marketplace  
- CUDA-only pipelines  
- Claiming regulatory or operational readiness without wet validation  

### Stretch soon after MVP

- One L2 MD template (AgI or feldspar slab + water) for “sexy deep dive”  
- Cooling-rate and deposition-mode modes  
- Particle size distribution → better INA/kg bridge  
- MacBook Air demo path (L0/L1 only)  

---

## Success metrics (90-day honest version)

You said success looks like:

1. **Payload confidence** — defend a viable amount/kg story to a rainmaking company  
2. **Sexy sim** — add novel candidates and get ranked results with confidence scores  

Translate to checkable goals:

| Goal | Done when |
|------|-----------|
| **Baselines behave** | AgI ranks above kaolinite-ish and well above inert/control in expected T window *directionally* |
| **INA/kg narrative** | For AgI (and one mineral), can state: “under assumptions X, effective activity ≈ Y per kg” with uncertainty band |
| **Novel intake** | Can add a SMILES or mineral name and get a ranked row + **Low/Medium/High** badge without crashing |
| **Demo in 10 minutes** | Cold start → load library → run screen → show rank table + one condition map |
| **Rainmaker literacy** | Can explain immersion vs deposition, why AgI, why dust, what the sim *doesn’t* prove |

**Hard truth:** “Buy payload and sell to rainmaker” eventually needs **wet-lab or supplier data**. The sim’s job is to **narrow candidates and make you fluent**, not replace field validation. Phrase external claims accordingly.

---

## Open items (for voice note + later)

- [ ] Finalize first 5–8 candidates  
- [ ] Define default particle assumptions for INA/kg (size, density, active fraction)  
- [ ] Pick “demo story” for Rainmaker (e.g. AgI vs feldspar vs novel organic under same T grid)  
- [ ] Decide CLI-first vs dashboard-first for week 1  
- [ ] Reflect on dual-use / communication tone for weather mod  
- [ ] See `voice-note-prompts.md` for free-association guide  

---

## File map

| File | Role |
|------|------|
| `Documents/INA-sim/INA-sim-mvp.md` | This file — locked decisions + summary |
| `Documents/INA-sim/voice-note-prompts.md` | What to free-associate tomorrow |

---

## Conversation log (condensed)

1. Wanted full INA simulation system for alternative INAs / conditions (T, rates, INA/kg), local-only, molecular geometry for minerals + molecules (AgI → feldspar → testosterone → novel).  
2. Got multi-fidelity architecture advice; MVP vs research traps; product = decision-support.  
3. Locked: mission A (weather mod / Rainmaker), organics secondary, general materials too far; laptop-only; want rank + T maps + INA/kg + deep dives + confidence scores; success = payload sell-story + sexy novel-candidate sim.  
4. Hardware checked; notes created; candidates proposed pending personal reflection.

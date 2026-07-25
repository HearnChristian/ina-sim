# Methods

Every equation INA-sim evaluates, with its symbols, units, source and range of
validity. If a number appears in the tool and not in this document, that is a
bug — file it.

Two layers run side by side and are never mixed:

| | heuristic layer | empirical layer |
|---|---|---|
| answers | "which of these would I try first?" | "what has anyone measured?" |
| output | relative score 0–1 vs AgI | ns(T) in m⁻², J(T), frozen fraction, T50 |
| basis | shaped activity curves | published fits with DOIs |
| lives in | `library/activity_curves.yaml` | `library/parameterizations.yaml` |
| honest use | ordering a shortlist | quoting a number |

The relative score is a convention. The empirical layer is evidence. The CLI
prints both and labels which is which.

---

## 1. Symbols and units

| symbol | quantity | unit | note |
|---|---|---|---|
| `T` | temperature | °C unless a name ends `_k` | sources vary; conversions in `units.py` |
| `ns(T)` | ice nucleation active site density | m⁻² (SI, internal) | sources often publish cm⁻² |
| `A` | particle surface area | m² | sphere-equivalent unless stated |
| `f` | frozen fraction of droplets | dimensionless, [0, 1] | the actual laboratory observable |
| `J_het` | heterogeneous nucleation rate coefficient | cm⁻² s⁻¹ | kept in source CGS on purpose |
| `J_hom` | homogeneous nucleation rate coefficient | cm⁻³ s⁻¹ | per liquid volume, not per area |
| `V` | droplet volume | m³ (converted to cm³ for `J_hom`) | |
| `σ_log10` | 1σ uncertainty of log₁₀(ns) | decades | from the source, or flagged as assumed |
| `T50` | median freezing temperature | °C | temperature where `f = 0.5` |

Terminology follows Vali et al. (2015): particles that nucleate ice are **ice
nucleating particles (INP)**, and `ns` has dimension L⁻².

Rate coefficients are deliberately **not** converted to SI. Every paper quotes
them in CGS; converting on the way in and out is how a factor of 10⁴ gets lost.

---

## 2. Singular description (Vali, 1971)

Active sites are treated as a fixed, temperature-ordered property of a surface.
Freezing is time independent. For droplets each carrying particle surface area
`A`:

```
f(T) = 1 - exp(-ns(T) · A)                              (1)
ns(T) = -ln(1 - f) / A                                  (2)   [inversion]
```

Equation (2) is undefined at `f = 0` (no information) and diverges at `f = 1`;
`ns_from_frozen_fraction` raises in both cases instead of returning a number.

The median freezing temperature solves `ns(T50) · A = ln 2`, found by bisection
inside the parameterization's validity range only. If the crossing lies outside
that range, `median_freezing_temperature` returns `None` rather than an
extrapolation dressed as a prediction.

INP concentration from an aerosol population uses the exact per-particle
activation probability, so it saturates at the number of particles present:

```
n_INP = N · (1 - exp(-ns · A_particle))                  (3)
```

not the linearised `N · ns · A`, which exceeds `N` when `ns·A` is large.
Implementation: `physics/freezing.py`.

## 3. Stochastic description (Murray et al., 2011)

Nucleation is a rate process, so the answer depends on how long droplets are
held cold. Survival probability over a time step `Δt`:

```
f = 1 - exp(-(J_hom · V + Σᵢ J_i · σᵢ) · Δt)             (4)
```

This is Eq. (18)–(19) of Murray et al. (2011). A cooling ramp integrates (4)
step by step, converting each temperature step to a dwell time from the cooling
rate: `Δt = (ΔT / rate) · 60 s`.

The two descriptions disagree, and that disagreement is physical, not a defect:
slower cooling freezes warmer under (4) and not at all under (1).
`compare_descriptions` reports the gap so it can be read as a bound on how much
of an answer is model choice.

---

## 4. The parameterizations

All entries live in `src/ina_sim/library/parameterizations.yaml` with their
units, area basis, validity range, uncertainty and reference key. Evaluate any
of them with `ina-sim ns --temp -20`.

### 4.1 Mineral INAS densities — Harrison et al. (2019)

`ns` in **cm⁻²**, `T` in °C, **BET** surface area basis. Quoted verbatim:

```
K-feldspar   log₁₀ ns = -3.25 - 0.793 T - 6.91e-2 T² - 4.17e-3 T³
                        - 1.05e-4 T⁴ - 9.08e-7 T⁵      (-3.5 … -37.5 °C; σ 0.8)
quartz       log₁₀ ns = -1.709 + 7e-2 T + 1.75e-2 T² + 2.66e-4 T³
                                                       (-10.5 … -37.5 °C; σ 0.8)
plagioclase  log₁₀ ns = -12 - 1.71 T - 0.106 T² - 3.17e-3 T³ - 3.24e-5 T⁴
                                                       (-12.5 … -38.5 °C; σ 0.5)
albite       log₁₀ ns = -2.29 - 1.79e-2 T + 1.89e-2 T² + 3.41e-4 T³
                                                       (-6.5 … -35.5 °C; σ 0.7)
```

The paper's own ordering claim — plagioclase least active, K-feldspar most
active, albite and quartz intermediate and similar — is enforced as a
validation anchor.

### 4.2 Desert dust — Niemand et al. (2012)

`ns` in **m⁻²**, `T` in °C, **geometric** (aerosol size distribution) basis:

```
ns(T) = exp(8.934 - 0.517 T)                            (-36 … -12 °C)
```

The source states no σ. INA-sim substitutes 1.0 decade — the spread Hiranuma
et al. (2015) found between 17 techniques measuring one sample — and marks the
result `sigma_assumed: true` everywhere it appears.

### 4.3 Kaolinite — Murray et al. (2011), Eq. (24)

Rate coefficient, `T` in **kelvin**, `J` in cm⁻² s⁻¹:

```
J_het(T) = exp(-0.8802 T + 222.17)                      (236.1 … 245.5 K)
```

### 4.4 Homogeneous freezing of pure water — Murray et al. (2010)

Per liquid **volume**, `T` in kelvin, `J` in cm⁻³ s⁻¹:

```
J_hom(T) = exp(-2.92 T + 706.5)                         (234.9 … 236.7 K)
```

A volume rate is not an area density. The comparison guard refuses to rank it
against any `ns`.

### 4.5 Silver iodide — derived here, not published

AgI has no published INAS parameterization. INA-sim derives one from the 19
usable immersion-freezing rows of Marcolli et al. (2016) Table 1, inverted with
Eq. (2) on sphere-equivalent geometric area:

```
log₁₀ ns[m⁻²] = 8.7913 - 0.2009 T                       (-22.2 … -5.2 °C)
n = 19, R² = 0.26, residual σ = 1.82 decades
```

**Read the R² before quoting the number.** Aerosol-generated AgI nanoparticles
sit up to 3.5 decades above cold-stage crystal studies at the same temperature.
Surface area does not describe AgI on its own — which is what the review itself
concludes. The fit is a central estimate with a wide, explicit band, and the
band is validated against the data it came from.

Regenerate with `python tools/fit_agi_ns.py`; the shipped coefficients and the
dataset hash are checked in CI.

### 4.6 Soluble salts — no ns exists

NaCl, CaCl₂ and KI are not ice nucleants. They depress the freezing point
colligatively and lower water activity, which **suppresses** freezing
(Koop et al., 2000):

```
ΔTf = i · Kf · b        Kf = 1.86 K kg mol⁻¹, ideal dilute limit
```

with van 't Hoff factors i = 2 (NaCl, KI) and 3 (CaCl₂). Beyond ~1 molal the
ideal law stops being quantitative and the result is flagged
`ideal_limit_exceeded`.

KI was reclassified from `ice_nucleant` to a soluble salt in v0.3.0. Its earlier
0.55 "efficiency" came from a supercooled-water calculator where KI was a
freezing-point depressant — the opposite effect. Sharing an iodide ion with AgI
confers no ice nucleation ability.

---

## 5. Importing your own experiment

```bash
ina-sim assay my_run.csv                    # invert + compare
ina-sim assay my_run.csv --out spectrum.csv # spectrum for plotting
ina-sim assay my_run.json --json            # everything, machine readable
```

A run is (temperature, droplets frozen, droplets total) plus the surface area
each droplet carries. Rows may be cumulative (default) or per-step
(`counting: differential`). CSV files may carry their own metadata as
`# key: value` header lines, so one file records both the data and the
conditions; CLI flags override them.

**Surface area, three ways.** Labs record it differently, so all three are
accepted and the route taken is reported back:

| route | inputs | typical basis |
|---|---|---|
| explicit | `surface_area_m2_per_droplet` | either |
| particles | `particle_diameter_um` × `particles_per_droplet` | geometric |
| suspension | `concentration_g_per_l` × `droplet_volume_ul` × `specific_surface_area_m2_per_g` | BET |

`area_basis` is **mandatory and has no default**. It decides which published
fits the result may be compared against; a run that does not record it cannot be
compared to anything without guessing.

**Inversion.** Eq. (2), per temperature step. Then:

**Counting uncertainty.** A frozen fraction is a binomial proportion from a
finite number of droplets, so the band comes from the **Wilson score interval**
rather than the normal approximation. Wilson is used specifically because the
Wald interval collapses to zero width at `f → 0` and `f → 1` — exactly where a
freezing curve begins and ends — and would claim perfect precision there.

**One-sided points.** `f = 0` and `f = 1` have no central ns, but they still
bound it from one side, so they are reported as `upper limit` / `lower limit`
rather than dropped. A saturated assay (`f = 1`) cannot see higher site
densities, and says so.

**Dynamic range.** An assay of `N` droplets each carrying area `A` can only
resolve

```
ns_min ≈ -ln(1 - 1/N) / A      (one droplet frozen)
ns_max = ln(N) / A             (one droplet unfrozen)
```

Points outside that window are artefacts of the experiment's size, not
properties of the sample, and are flagged. More droplets widen the window at
both ends.

**Comparison.** Each usable point is compared against every singular ns fit on
the *same* area basis that covers that temperature, reporting bias, RMSE and max
residual in decades, plus the fraction of points falling inside that fit's own
σ band. Fits on a different basis, and rate parameterizations, are excluded
rather than compared with a caveat.

**What is not propagated.** Temperature calibration error and surface-area
uncertainty are usually *larger* than the counting error, and INA-sim does not
propagate them. Every spectrum prints that caveat. Vali's differential spectrum
`k(T)` is also not computed.

`examples/kfeldspar_synthetic_assay.csv` shows the file format. It is clearly
labelled synthetic — simulated from the K-feldspar fit by
`tools/make_example_assay.py` — and the round-trip test requires that importing
it recovers the fit it came from (bias < 0.3 decades) while rejecting quartz and
plagioclase.

## 6. Polydisperse aerosol and INP concentration

```bash
ina-sim aerosol --id desert_dust_niemand2012 --temp -20 \
  --mode 1.0:0.8:1.9:accumulation --mode 0.01:4:2.2:coarse
```

Elsewhere a particle population is monodisperse spheres, which is fine for one
material at one size and wrong for atmospheric work. A lognormal mode with count
median diameter `D_g` and geometric standard deviation `σ_g` has the
Hatch-Choate moments (Seinfeld and Pandis, 2016):

```
<D^k> = D_g^k exp(k² ln²σ_g / 2)                          (5)
S_tot = N π D_g² exp(2 ln²σ_g)                            (6)
V_tot = N (π/6) D_g³ exp(4.5 ln²σ_g)                      (7)
```

**INP concentration is not `ns · S_tot`.** That linearisation counts several
active sites on one particle as several INP and can exceed the number of
particles present. The reported quantity integrates the per-particle activation
probability over the distribution:

```
n_INP = ∫ n(D) [1 - exp(-ns π D²)] dD                     (8)
```

which reduces to `ns · S_tot` only when `ns·A ≪ 1`. Both are printed with their
ratio, so the regime is visible rather than assumed. Integration is uniform in
`ln D` over ±5 `ln σ_g`, midpoint rule; the binned surface area reproduces the
analytic moment (6) to better than 0.2%.

**Size decides, not number.** Surface area goes as `D²`, so a coarse mode with
a thousand times fewer particles can supply comparable INP. The output reports
`d50` — the median diameter of the particles actually supplying the INP — and
the share coming from particles above 1 µm.

**Truncation.** Instruments count over a finite size range, and a
parameterization built on "particles larger than 0.5 µm" is not comparable to an
untruncated integral. `--d-min` / `--d-max` make that explicit and the result is
labelled truncated.

## 7. Intercomparison: how much do the fits disagree?

```bash
ina-sim compare --range=-35:-10:5
ina-sim compare --temp -20 --basis BET
```

Fits are grouped by `(quantity, surface-area basis)`. Fits in different groups
are not comparable at all — a BET ns, a geometric ns and a rate coefficient are
three different quantities wearing similar symbols.

Within a group two numbers are reported, and the distinction between them is the
entire point:

- **range** — max − min across the row. For fits of *different* materials this
  is a real difference between substances, not a disagreement. K-feldspar
  sitting four decades above plagioclase is mineralogy.
- **CONFLICT** — flagged only when two fits share a `material_key` *and* their
  σ bands fail to overlap (`gap > √(σ_a² + σ_b²)`). That is the literature
  actually contradicting itself.

This build contains **no two fits of the same material**, so it reports zero
conflicts and says so: the disagreement question is not answerable until a
second fit for an existing material is added. Adding one (Atkinson et al. 2013
alongside Harrison et al. 2019 for K-feldspar, or Ullrich et al. 2017 alongside
Niemand et al. 2012 for dust) is the obvious next step, and it will light this
view up without any code change.

## 8. Coverage: which view sees what

```bash
ina-sim rank --temp -20        # every measured material, heuristic layer off
```

Two screening views, with different coverage, and the difference is the point:

| view | covers | ordering | needs a library entry |
|---|---|---|---|
| `ina-sim screen` | the 8 library candidates | relative score 0–1 vs AgI | yes |
| `ina-sim rank` | every material with a fit (8 parameterizations) | log₁₀ of the measured quantity | no |

Four materials — quartz, plagioclase, albite and desert dust — have published
fits but **no library candidate**, and they are deliberately not forced into the
heuristic screen. Doing so would require inventing a peak strength and an
activity curve for each, and the arithmetic shows why that fails: normalising a
quantity spanning ten decades onto a linear 0–1 axis puts quartz at 0.0012 and
plagioclase at 0.00002, i.e. visually inert, for minerals that demonstrably
nucleate ice. `ina-sim rank` reports them in log₁₀, which is how the field reads
ns, and needs no invented fields at all.

The remaining honest gaps, in order of what would help most:

1. **No two fits describe the same material**, so `ina-sim compare` cannot yet
   test whether the literature disagrees (see §7). Atkinson et al. (2013) for
   K-feldspar or Ullrich et al. (2017) for dust would fix this; neither is open
   access and neither is transcribed here, because a coefficient that cannot be
   verified does not ship. See [PAPERS-WANTED.md](PAPERS-WANTED.md) for what
   each one unlocks and how to obtain it.
2. **Desert dust has no honest place on the relative scale.** Its only
   same-basis anchor is the AgI fit derived here, whose σ is 1.8 decades — too
   uncertain to anchor anything. It stays registry-only until a better AgI
   parameterization exists.
3. **Kaolinite is a rate coefficient valid only over 236–245 K**, so it returns
   nothing at mixed-phase temperatures where it is most often used.

## 9. What the screening inputs do

```bash
ina-sim figures --out reference-figures.html   # or Physics ▸ Reference figures in the GUI
```

A control that changes nothing is not automatically a defect. Two of the
screening inputs are inert because the physics says so, and two were inert
because the model was thin. The second pair is now fixed.

| input | effect | why |
|---|---|---|
| temperature | strong | ns(T) rises ~0.2–0.4 decades per kelvin |
| **particle diameter** | **strong (new)** | `P_act = 1 − exp(−ns·πd²)`, so area and effect scale as d² |
| **seeding density** | **linear on n_INP (new)** | `n_INP = N · P_act`, uncapped |
| relative humidity | none in immersion, strong in deposition | an immersed particle is already in liquid water |
| pressure | none on nucleation | sets the parcel's water inventory instead |

**The size fix.** For materials with a parameterization the activation
probability uses the measured ns(T). For the rest there is no ns, so the
heuristic score is *reinterpreted* as the activation probability of a 1 µm
particle:

```
ns_eff(T) = -ln(1 - η(T)) / (π·d_ref²)                    (9)
```

This is a convention, labelled as one wherever it appears. Its virtue is
exactness at the reference: at d = 1 µm the activation probability equals the
score the tool has always reported, so nothing that already worked moves, while
away from 1 µm the scaling is the physical d² instead of nothing.

**What is deliberately unchanged.** The relative score itself stays
size-independent, so rankings and the demo table cannot shift when the diameter
slider moves. The score also keeps its legacy loading factor `min(1, N/50)`,
which saturates for no physical reason; it is retained because "zero dose gives
zero score" is a tested property and because it multiplies every candidate
equally and so cannot reorder anything. **Read n_INP, not the score, for
anything dose related.**

**Overseeding is not modelled.** Real seeding does saturate — too many ice
crystals compete for the same vapour and none grows to precipitation size — but
that is a vapour budget and growth problem, not a nucleation one.

### Reference figures

Eight static plots generated from the registry itself, so they cannot drift from
the numbers the tool uses: ns(T) per area basis with uncertainty bands, the AgI
measurement scatter against its fit, T₅₀ against particle diameter, predicted
frozen fraction, INP concentration from a dust loading (exact integral vs the
`ns × S_tot` shortcut), homogeneous freezing by cooling rate, and the resolvable
n_s window against droplet count. Inline SVG, no scripts, no external assets.

They are static on purpose: they are not about one parcel of air, they are the
evidence the tool rests on. Every curve stops where its source's fitted range
stops.

## 10. Rules the code enforces

**No silent extrapolation.** Outside the temperature range its source fitted, a
parameterization returns nothing. `--extrapolate` overrides this and stamps the
result `EXTRAPOLATED` with a note that the source does not support it.

**No mixing area bases.** BET and geometric surface areas differ by more than an
order of magnitude for fine-grained samples (Hiranuma et al., 2015), so
`assert_comparable` raises `AreaBasisError` on any attempt to rank ns values
across bases, or to compare a density with a rate.

**No unstated uncertainty.** Where a source gives no σ, the substituted default
is documented, attributed and flagged rather than hidden.

**No unreferenced numbers.** Every parameterization and anchor names a key in
`library/references.yaml`; `tests/test_validation_and_references.py` fails the
build if one does not resolve, if a reference cannot be located by DOI, URL or
publisher, or if the bibliography grows an entry nothing uses.

**No unmeasured material presented as measured.** Each screened candidate
carries an evidence block: `measured`, `solute`, or `none`. Most of the library
is `none`, and it says so in the CLI output.

---

## 11. What this still is not

- Not a calibration to any specific field campaign or seeding operation.
- Not a source of operational rates, dosages or precipitation forecasts.
- Not a substitute for a droplet-freezing assay: it predicts what one would
  measure, which is a claim that can be checked, not a measurement.
- Not complete: eight parameterizations covering four library candidates, and
  no two of them describe the same material, so it cannot yet tell you where
  the literature disagrees. The gaps are visible on purpose
  (`ina-sim ns --list`, `ina-sim compare`).

## 12. References

`ina-sim refs` prints the bibliography with DOIs and how each source was used.
See also [REFERENCES.md](REFERENCES.md).

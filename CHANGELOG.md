# Changelog

Notable changes, newest first. Versions follow [semantic versioning](https://semver.org/);
before 1.0 the minor number moves when a capability lands and the patch number
when behaviour is corrected.

Defects introduced by this project and later fixed are listed as plainly as the
features. A changelog that only records wins is not a record.

## 0.4.1 — hardening

**Added**
- `ina-sim doctor`: one command that runs every self-check — environment,
  registry integrity and monotonicity, validation anchors, derived-fit
  freshness, generated-doc freshness, audit-chain integrity — and exits non-zero
  if any fails.
- In-process CLI test suite covering every subcommand, its `--json` output and
  its failure modes. Coverage of `cli.py` went from an unmeasured 0% to 83%;
  the module was always tested, but only through subprocesses, which coverage
  cannot see.
- Coverage measured and gated in CI at 80%.
- Packaging verified in CI: build a wheel, install it into a clean environment,
  run the CLI from it.
- `CITATION.cff`, `CHANGELOG.md`, pre-commit hooks, PR template.

## 0.4.0 — decision layer and audit trail

**Added**
- `ina-sim scenario`: payload mass → particle count (Hatch-Choate third moment)
  → number concentration → delivered INP with a Monte Carlo band → probability
  of clearing a threshold. Runs backwards with `--target-probability`, bisecting
  on payload mass, and returns *none* when no payload reaches the target rather
  than an absurd number.
- A claims guardrail printed with every scenario: what the result supports
  saying, what it supports only alongside stated caveats, and what it does not
  support at all (precipitation, efficacy, causation).
- `ina-sim history`: hash-chained append-only run log carrying a fingerprint of
  `parameterizations.yaml`, so `--diff` attributes a moved number to *the
  conditions changed*, *the science changed*, or neither.
- GUI: reference figures under View, cursor tips under Help, temperature sweep
  under Physics with a quantity selector (score / activation probability / INP
  per litre).

**Fixed**
- A measured material outside its fitted temperature range silently fell back to
  the heuristic-derived n_s. K-feldspar jumped from 2.2e-7 to 1.0e+1 INP/L
  between −3.5 and −3.0 °C — seven orders of magnitude from a change of source,
  not physics. This is what made the temperature sweep look like noise. Such a
  material now returns no value, the same refusal `ns()` already made.
- Rate coefficients were being used as site densities: kaolinite's J in
  cm⁻² s⁻¹ was fed to a formula expecting n_s in m⁻². Rate-measured materials
  now report no activation, because converting a rate needs a dwell time a
  steady-state screen does not have.
- Activation probabilities are no longer rounded to six decimal places, which
  had displayed 0 beside a non-zero INP concentration.

## 0.3.5 — Monte Carlo uncertainty

**Added**
- `ina-sim uncertainty`: samples n_INP with log-normal n_s (the convention the
  literature states σ in), normal temperature, and log-normal aerosol error;
  reports percentiles, the 90% spread in decades, and P(above threshold).
- Variance decomposition by freezing each input under common random numbers.
  For the standard dust case n_s owns 96% of the spread, which says a better
  optical counter would not move the answer.
- Deterministic per seed, with the seed reported and reproducibility checked in
  CI by diffing two runs.

## 0.3.4 — size and dose

**Added**
- Particle diameter acts through `P = 1 − exp(−n_s·πd²)`, exact at the 1 µm
  reference so nothing that already worked moved; seeding density drives an
  uncapped INP concentration.
- Nine static reference figures generated from the registry, rendered by a
  stdlib SVG module so the page stays offline and self-contained.
- Pressure and immersion-mode humidity documented as *correctly* inert, with a
  test that fails if anyone adds fake sensitivity.

## 0.3.3 — coverage without invention

**Added**
- `ina-sim rank`: empirical-only ranking in log₁₀ covering all parameterizations,
  not just the four with library entries.

**Notes**
- Deriving library entries for quartz, plagioclase and albite from their fits
  was tried and rejected: normalising a ten-decade quantity onto a linear 0–1
  axis puts quartz at 0.0012, i.e. visually inert, for a mineral that
  demonstrably nucleates ice.

## 0.3.2 — aerosol and intercomparison

**Added**
- `ina-sim aerosol`: lognormal modes → INP concentration by the exact activation
  integral rather than `n_s × S_tot`, with the d50 of the particles actually
  supplying the nucleation.
- `ina-sim compare`: fits grouped by quantity and area basis, separating *range
  across materials* (mineralogy) from a genuine same-material conflict.

**Fixed**
- The first draft flagged CONFLICT on every row of the mineral group. Those are
  four different minerals; `material_key` now makes the distinction data rather
  than inference.

## 0.3.1 — bring your own experiment

**Added**
- `ina-sim assay`: import a droplet-freezing run (CSV/JSON, three surface-area
  routes), invert it with Vali (1971), band it with Wilson score intervals,
  flag the range the droplet count can resolve, and score it against every
  published fit on the same area basis.

## 0.3.0 — the empirical layer

**Added**
- A registry of published n_s(T) and J(T) parameterizations, each with units,
  surface-area basis, fitted range, stated uncertainty and DOI.
- Rules enforced in code: no silent extrapolation, no mixing surface-area bases,
  no unstated uncertainty, no unreferenced numbers.
- A validation suite that re-derives published claims, run in CI.

**Fixed**
- KI was classified as an ice nucleant with an efficiency of 0.55, inherited
  from a supercooled-water calculator where it was a freezing-point depressant —
  the opposite effect. It is a soluble salt and is now treated as one.

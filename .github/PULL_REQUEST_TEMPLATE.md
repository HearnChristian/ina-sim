## What this changes

<!-- One or two sentences. -->

## If this touches the empirical layer

Delete this section if it does not.

- [ ] Every new coefficient names a key in `library/references.yaml`
- [ ] `quote` carries the source's own wording (published fits) **or**
      `derivation` + `dataset` are set (fits derived in this repo)
- [ ] `ns_units`, `area_basis`, `t_min_c`, `t_max_c` and `sigma_log10` are set;
      a null sigma is deliberate and the substitute is documented
- [ ] At least one validation anchor that is **independent of the coefficients**
      — a claim in the paper's prose, an ordering it asserts, or a regime the
      result must land in
- [ ] `python tools/gen_docs.py` run, generated docs committed

## Checks

- [ ] `ina-sim doctor` passes
- [ ] `pytest -q` passes
- [ ] `ruff check src tests tools` and `mypy` clean

## What this does not claim

<!-- If this adds a capability, state what it still cannot support saying.
     That statement is a feature of this repository, not paperwork. -->

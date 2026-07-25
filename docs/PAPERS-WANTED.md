# Papers wanted

Sources that would close a named gap in `docs/METHODS.md` §8 but are not open
access. Nothing from these is transcribed into the repo, because a coefficient
that cannot be verified does not ship.

If you obtain one, what is needed is small: the **equation, its coefficients,
the units of ns, whether T is °C or K, the fitted temperature range, and the
stated uncertainty**. That is enough to add a registry entry plus a validation
anchor.

## Free routes to try first, in order

1. **A university library proxy.** If you have any current enrolment, the
   library login gets you all four immediately. Fastest route by far.
2. **Institutional repositories.** Authors deposit accepted manuscripts legally
   and for free:
   - University of Leeds → White Rose Research Online, `eprints.whiterose.ac.uk`
   - KIT (Karlsruhe) → KITopen, `publikationen.bibliothek.kit.edu`
3. **ResearchGate "Request full-text"** — one click, goes to the author.
4. **Email the corresponding author.** Asking an author for a copy of their own
   paper is normal academic practice and usually answered within a few days. A
   two-line request naming the paper and what you're building is plenty.

## The list, most useful first

### 1. Ullrich et al. (2017) — biggest single unlock

*A New Ice Nucleation Active Site Parameterization for Desert Dust and Soot*,
J. Atmos. Sci. 74, 699–717 · doi:10.1175/JAS-D-16-0074.1 · AMS (journals.ametsoc.org,
returns HTTP 403 to automated fetches)

**Unlocks two gaps at once:** a second desert-dust fit, giving the first
same-material pair so `ina-sim compare` can finally test whether the literature
disagrees; and `ns(T, S_ice)` for **deposition nucleation**, a mode the tool
currently has zero parameterizations for.

Authors at KIT, Institute of Meteorology and Climate Research (IMK-AAF):
R. Ullrich, C. Hoose, O. Möhler, T. Leisner. Try KITopen first. I do not have a
verified email for this group — use the KIT staff directory rather than a
guessed address.

### 2. Atkinson et al. (2013) — turns on conflict detection

*The importance of feldspar for ice nucleation by mineral dust in mixed-phase
clouds*, Nature 498, 355–358 · doi:10.1038/nature12278

**Unlocks:** the original K-feldspar ns(T), which would sit alongside
Harrison et al. (2019) as the first same-material pair in the BET group.
Harrison's own §5.2 says the Atkinson fit "is a relatively poor predictor …
especially at temperatures colder than about −15 °C", so this pair should
produce a genuine, citable CONFLICT — exactly what `ina-sim compare` was built
to surface.

Corresponding author **Benjamin J. Murray, University of Leeds —
`b.j.murray@leeds.ac.uk`** (address as published in his open-access papers
Murray et al. 2011 and Broadley et al. 2012). Leeds deposits in White Rose, so
check there first.

### 3. Niemand et al. (2012) — verify what is currently second-hand

*A particle-surface-area-based parameterization of immersion freezing on desert
dust particles*, J. Atmos. Sci. 69, 3077–3092 · doi:10.1175/JAS-D-11-0249.1

The coefficients in the registry (`a = 8.934`, `b = −0.517`) come from the
verbatim restatement in Kanji et al. (2019), ACP 19, 5091–5110, which is open
access. Getting the primary would (a) confirm that transcription and (b) supply
the **stated uncertainty**, which the source restatement does not give — INA-sim
currently substitutes 1.0 decade and flags every dust result `sigma_assumed`.

KIT again (Niemand, Möhler, Leisner). Same route as #1.

Related and already open: Kanji et al. (2019) can be checked directly at
doi:10.5194/acp-19-5091-2019 — corresponding author **Zamin Kanji, ETH Zürich —
`zamin.kanji@env.ethz.ch`**, if you want the restatement confirmed.

### 4. Murray et al. (2010) — primary for homogeneous freezing

*Kinetics of the homogeneous freezing of water*, Phys. Chem. Chem. Phys. 12,
10380–10387 · doi:10.1039/c003297b

Lower priority: `J_hom(T) = exp(−2.92 T + 706.5)` is already transcribed from
Murray et al. (2011) Eq. (23), which is open access and passes the homogeneous
freezing validation anchor. The primary would confirm the range and uncertainty.

Same contact as #2 (Murray, Leeds), same White Rose route.

## Not needed

- **Koop et al. (2000)**, doi:10.1038/35020537 — cited only for the *direction*
  of the solute effect, which is not in dispute. No coefficient is taken from it.
- **Pruppacher & Klett (1997)**, **Seinfeld & Pandis (2016)**, **CRC Handbook** —
  textbooks, used for standard relations. Any library copy works.

## What happens when one arrives

Hand me the equation and its stated range and uncertainty. I add a row to
`library/parameterizations.yaml`, a reference entry, and at least one validation
anchor that is independent of the coefficients, then the tests and CI enforce it
from then on. For a same-material fit, `ina-sim compare` starts reporting
CONFLICT rows automatically — no code change needed.

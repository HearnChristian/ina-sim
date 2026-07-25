# 90-second demo script (Rainmaker / portfolio)

**Goal:** cold start → honest table → literature check → limitations in under 90s.

## Prep (once)

```bash
cd ~/ina-sim && source .venv/bin/activate
ina-sim gui
```

Hard-refresh browser if the page was already open.

## Beat sheet

| t | Action | Say |
|---|--------|-----|
| 0–10s | Open GUI, point at Win95 chrome | “Local screening lab — learning + portfolio, not a product.” |
| 10–25s | Set T ≈ −10 °C, track **Ice**, starter set on | “Mixed-phase immersion conditions. Ice track demotes CCN salts.” |
| 25–40s | **Run Screen** | “AgI baseline; K-feldspar above kaolinite — matches mineral IN literature direction.” |
| 40–55s | Point at **relINA band** + **source/citation** column | “Uncertainty bands by confidence tier. Every η has a source.” |
| 55–70s | Point at **Literature xref ✓** + assumptions panel | “Automated checks against public research direction — not ns(T) calibration.” |
| 70–85s | Optional: upload SMILES, uncheck starter, re-run | “Builder feed — exploratory only until molecular builder.” |
| 85–90s | Close | “What it doesn’t do: operational rates, radar, wet-lab replacement.” |

## Screenshot checklist

1. Results table with AgI / feldspar / kaolinite order  
2. Literature xref pass line  
3. Assumptions panel visible  
4. Mechanism banner: ICE / GLACIOGENIC  

## Fail the demo if

- NaCl ranks above AgI on ice track at −10 °C  
- Export claims operational guidance  
- No uncertainty or source visible  
- `ina-sim validate` does not come back green

## Appendix: "where do these numbers come from?"

Not part of the 90 seconds. Use it when someone technical pushes back — this is
the part that separates a demo from a tool.

```bash
ina-sim ns --list          # 8 parameterizations, 7 published + 1 derived here
ina-sim ns --temp -20      # ns(T) with units, area basis, sigma and citation
ina-sim validate           # 5 anchors re-derived against published claims
ina-sim refs --key harrison2019
```

Three answers worth having ready:

- **"Is the ranking measured?"** No. The relative score is a ranking
  convention; the empirical layer is separate and reports which candidates have
  a published ns(T) at all. Most do not, and the CLI prints that count.
- **"How good is the AgI number?"** Derived here from Marcolli et al. (2016)
  Table 1: R² = 0.26, σ = 1.8 decades. Sixty years of AgI experiments do not
  collapse onto one surface-area scaling — the review reaches the same
  conclusion. The band is wide because the evidence is.
- **"Why is K-feldspar below desert dust at −12 °C?"** Different surface-area
  bases: BET for the mineral fits, geometric for the dust fit. The tool refuses
  to rank across bases rather than quietly comparing them.

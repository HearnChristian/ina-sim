"""The reference figure set.

Static plots of what the literature actually says, drawn straight from the
registry so they cannot drift from the numbers the tool uses. Nothing here
depends on the slider state - that is the point. These are the figures you would
put in front of someone who asked "what does this field know?", and they answer
the question the interactive screen cannot: how large the uncertainties are and
how far apart the materials sit.

Every figure is generated from `library/parameterizations.yaml` and the digitized
AgI dataset. Change a coefficient and the figures change with it.
"""

from __future__ import annotations

import math
from typing import Any

from ina_sim.figures.svg import PALETTE, Axis, Figure, Series, figure_block
from ina_sim.physics.aerosol import LognormalMode, SizeDistribution, inp_spectrum
from ina_sim.physics.dose import REFERENCE_DIAMETER_UM
from ina_sim.physics.freezing import (
    frozen_fraction_singular,
    median_freezing_temperature,
    stochastic_freezing_curve,
)
from ina_sim.physics.ns import evaluate, get_parameterization, load_parameterizations
from ina_sim.units import (
    micrometres_to_metres,
    sphere_surface_area_m2,
    sphere_volume_m3,
)
from ina_sim.validation.runner import load_dataset

STEP_C = 0.5


def _grid(param, step: float = STEP_C) -> list[float]:
    n = int(round((param.t_max_c - param.t_min_c) / step))
    return [param.t_max_c - i * step for i in range(n + 1)]


def fig_ns_by_basis(area_basis: str) -> dict[str, Any]:
    """ns(T) for every fit on one area basis, with stated uncertainty bands."""
    params = [
        p
        for p in load_parameterizations().values()
        if p.quantity == "ns" and p.area_basis == area_basis
    ]
    params.sort(key=lambda p: p.material_key)
    series = []
    for i, param in enumerate(params):
        temps = _grid(param)
        values, lows, highs = [], [], []
        for temp in temps:
            est = evaluate(param, temp)
            values.append(est.value or float("nan"))
            lows.append(est.low or float("nan"))
            highs.append(est.high or float("nan"))
        series.append(
            Series(
                label=param.material_key,
                xs=temps,
                ys=values,
                band_low=lows,
                band_high=highs,
                colour=PALETTE[i % len(PALETTE)],
                dashed=param.status == "derived",
            )
        )
    fig = Figure(
        title=f"Ice nucleation active site density, {area_basis} surface area",
        x=Axis("temperature (°C)", invert=True),
        y=Axis("n_s  (m⁻²)", scale="log10"),
        series=series,
    )
    fig.caption = (
        f"Every parameterization in this build measured on a {area_basis} area "
        "basis, each drawn only across the temperature range its source fitted. "
        "Shaded bands are the stated 1σ uncertainty, or the documented "
        "substitute where a source gives none. Dashed lines are derived in this "
        "repository rather than published. Curves on different area bases are "
        "on separate figures because they cannot be compared."
    )
    return figure_block(fig, "; ".join(sorted({p.as_dict()["citation"] for p in params})))


def fig_frozen_fraction() -> dict[str, Any]:
    """What a droplet assay would actually see, for a 1 µm particle."""
    area = sphere_surface_area_m2(micrometres_to_metres(REFERENCE_DIAMETER_UM))
    series = []
    params = [
        p for p in load_parameterizations().values() if p.quantity == "ns"
    ]
    params.sort(key=lambda p: p.material_key)
    for i, param in enumerate(params):
        temps = _grid(param, 0.25)
        fractions = []
        for temp in temps:
            est = evaluate(param, temp)
            fractions.append(
                frozen_fraction_singular(est.value, area) if est.value else 0.0
            )
        series.append(
            Series(
                label=param.material_key,
                xs=temps,
                ys=fractions,
                colour=PALETTE[i % len(PALETTE)],
                dashed=param.status == "derived",
            )
        )
    fig = Figure(
        title=f"Predicted frozen fraction, one {REFERENCE_DIAMETER_UM:g} µm particle per droplet",
        x=Axis("temperature (°C)", invert=True),
        y=Axis("fraction of droplets frozen", lo=0.0, hi=1.0),
        series=series,
    )
    fig.caption = (
        "The same parameterizations expressed as the observable a cold stage "
        "reports. This is the quantity to compare against your own run with "
        "`ina-sim assay`. Curves stop where their source's fitted range stops. "
        "Materials on different area bases appear together here only because "
        "the frozen fraction is a probability, not a density - the underlying "
        "n_s values still must not be ranked against each other."
    )
    return figure_block(fig)


def fig_size_dependence() -> dict[str, Any]:
    """Why the particle-size slider matters: T50 against diameter."""
    diameters = [0.05 * (1.35**i) for i in range(22)]
    series = []
    params = [
        p for p in load_parameterizations().values() if p.quantity == "ns"
    ]
    params.sort(key=lambda p: p.material_key)
    for i, param in enumerate(params):
        xs, ys = [], []
        for d in diameters:
            area = sphere_surface_area_m2(micrometres_to_metres(d))
            t50 = median_freezing_temperature(param, area)
            if t50 is not None:
                xs.append(d)
                ys.append(t50)
        if xs:
            series.append(
                Series(
                    label=param.material_key,
                    xs=xs,
                    ys=ys,
                    colour=PALETTE[i % len(PALETTE)],
                    dashed=param.status == "derived",
                )
            )
    fig = Figure(
        title="Median freezing temperature against particle diameter",
        x=Axis("particle diameter (µm)", scale="log10"),
        y=Axis("T₅₀ (°C)"),
        series=series,
    )
    fig.caption = (
        "Surface area scales as d², so a ten-fold larger particle carries a "
        "hundred times the active sites and freezes several degrees warmer. "
        "Marcolli et al. (2016) measured roughly a 28 K shift between 20 nm and "
        "40 nm AgI particles. Curves end where T₅₀ leaves the fitted range - "
        "the tool refuses to extrapolate rather than continuing the line."
    )
    return figure_block(fig)


def fig_agi_scatter() -> dict[str, Any]:
    """The AgI evidence, shown rather than summarised."""
    data = load_dataset("agi_marcolli2016_table1.yaml")
    param = get_parameterization("agi_marcolli2016_derived")

    xs, ys = [], []
    for row in data.get("measurements", []):
        if not row.get("use_in_fit", False):
            continue
        frozen = float(row["frozen_fraction"])
        if not 0.0 < frozen < 1.0:
            continue
        area = float(row["particles_per_droplet"]) * sphere_surface_area_m2(
            float(row["diameter_nm"]) * 1e-9
        )
        xs.append(float(row["temperature_k"]) - 273.15)
        ys.append(-math.log(1.0 - frozen) / area)

    temps = _grid(param)
    fit, low, high = [], [], []
    for temp in temps:
        est = evaluate(param, temp)
        fit.append(est.value or float("nan"))
        low.append(est.low or float("nan"))
        high.append(est.high or float("nan"))

    fig = Figure(
        title="Silver iodide: sixty years of measurements, and the fit through them",
        x=Axis("temperature (°C)", invert=True),
        y=Axis("n_s  (m⁻², geometric area)", scale="log10"),
        series=[
            Series(
                label="fit ±1σ",
                xs=temps,
                ys=fit,
                band_low=low,
                band_high=high,
                colour=PALETTE[1],
                dashed=True,
            ),
            Series(
                label="measurements",
                xs=xs,
                ys=ys,
                colour=PALETTE[7],
                points_only=True,
            ),
        ],
    )
    fig.caption = (
        "Each point is one published immersion-freezing measurement from "
        "Marcolli et al. (2016) Table 1, inverted with the singular "
        "approximation. The fit through them has R² = 0.26 and a residual "
        "scatter of 1.8 orders of magnitude: aerosol-generated nanoparticles "
        "sit up to 3.5 decades above cold-stage crystals at the same "
        "temperature. AgI ice nucleation is not a function of surface area "
        "alone, which is the review's own conclusion. This figure is why the "
        "AgI band in this tool is wide."
    )
    return figure_block(fig, "Marcolli et al. (2016), doi:10.5194/acp-16-8915-2016")


def fig_inp_concentration() -> dict[str, Any]:
    """What a dust loading delivers, per litre of air."""
    dist = SizeDistribution(
        modes=(
            LognormalMode(1.0, 0.8, 1.9, "accumulation"),
            LognormalMode(0.01, 4.0, 2.2, "coarse"),
        )
    )
    param = get_parameterization("desert_dust_niemand2012")
    rows = inp_spectrum(dist, param, step_c=0.5)
    fig = Figure(
        title="INP concentration from a desert dust loading",
        x=Axis("temperature (°C)", invert=True),
        y=Axis("n_INP  (per litre)", scale="log10"),
        series=[
            Series(
                label="exact integral ±1σ",
                xs=[r.temperature_c for r in rows],
                ys=[r.n_inp_per_litre for r in rows],
                band_low=[r.n_inp_low_per_litre or float("nan") for r in rows],
                band_high=[r.n_inp_high_per_litre or float("nan") for r in rows],
                colour=PALETTE[0],
            ),
            Series(
                label="linear n_s × S_tot",
                xs=[r.temperature_c for r in rows],
                ys=[r.n_inp_linear_per_litre for r in rows],
                colour=PALETTE[1],
                dashed=True,
            ),
        ],
    )
    fig.caption = (
        "Two lognormal modes (1 cm⁻³ at 0.8 µm, σ_g 1.9; 0.01 cm⁻³ at 4 µm, "
        "σ_g 2.2) integrated against the dust parameterization. The dashed line "
        "is the familiar n_s × S_tot shortcut, which counts several active sites "
        "on one particle as several INP; the solid line integrates the "
        "per-particle activation probability and saturates correctly at the "
        "number of particles present. The gap between them is the error the "
        "shortcut introduces at low temperature."
    )
    return figure_block(fig, "Niemand et al. (2012), doi:10.1175/JAS-D-11-0249.1")


def fig_homogeneous() -> dict[str, Any]:
    """The homogeneous limit, and its cooling-rate dependence."""
    param = get_parameterization("water_homogeneous_murray2010")
    volume = sphere_volume_m3(micrometres_to_metres(10.0))
    series = []
    for i, rate in enumerate((0.1, 1.0, 10.0)):
        rows = stochastic_freezing_curve(
            None,
            particle_area_m2=0.0,
            droplet_volume_m3=volume,
            hom_param=param,
            cooling_rate_k_per_min=rate,
            t_start_c=param.t_max_c,
            t_end_c=param.t_min_c,
            step_c=0.01,
        )
        series.append(
            Series(
                label=f"{rate:g} K/min",
                xs=[r["T_c"] for r in rows],
                ys=[r["frozen_fraction"] for r in rows],
                colour=PALETTE[i],
            )
        )
    fig = Figure(
        title="Homogeneous freezing of pure 10 µm droplets, by cooling rate",
        x=Axis("temperature (°C)", invert=True),
        y=Axis("fraction frozen", lo=0.0, hi=1.0),
        series=series,
    )
    fig.caption = (
        "Homogeneous freezing is a rate process, so the answer depends on how "
        "long the droplets are held: a hundred-fold slower ramp freezes them "
        "measurably warmer. Nothing in the singular n_s description can "
        "represent this, which is why both descriptions are carried separately. "
        "The curves span only the 234.9–236.7 K range the source fitted."
    )
    return figure_block(
        fig, "Murray et al. (2010) via Murray et al. (2011), doi:10.5194/acp-11-4191-2011"
    )


def fig_assay_dynamic_range() -> dict[str, Any]:
    """What your own experiment can and cannot resolve."""
    counts = [10, 30, 100, 300, 1000]
    area = sphere_surface_area_m2(micrometres_to_metres(REFERENCE_DIAMETER_UM))
    lows = [-math.log1p(-1.0 / n) / area for n in counts]
    highs = [math.log(n) / area for n in counts]
    fig = Figure(
        title="Resolvable n_s window against droplet count (1 µm particle per droplet)",
        x=Axis("droplets in the assay", scale="log10"),
        y=Axis("n_s  (m⁻²)", scale="log10"),
        series=[
            Series(label="upper limit  ln(N)/A", xs=counts, ys=highs, colour=PALETTE[0]),
            Series(
                label="lower limit  −ln(1−1/N)/A",
                xs=counts,
                ys=lows,
                colour=PALETTE[1],
            ),
        ],
    )
    fig.caption = (
        "A droplet-freezing assay can only measure site densities between one "
        "droplet frozen and one droplet unfrozen. Outside that window the "
        "result reflects how many droplets were counted, not the sample. "
        "Quadrupling the droplet count buys roughly half a decade at each end - "
        "`ina-sim assay` flags points that fall outside it."
    )
    return figure_block(fig, "Vali (1971) singular inversion")


def fig_exceedance() -> dict[str, Any]:
    """The decision-shaped plot: probability of clearing a threshold."""
    from ina_sim.physics.uncertainty import propagate_inp

    param = get_parameterization("desert_dust_niemand2012")
    result = propagate_inp(
        param,
        temperature_c=-20.0,
        number_per_cm3=1.0,
        median_diameter_um=0.8,
        geometric_sd=1.9,
        samples=4000,
    )
    thresholds = [10 ** (-3.0 + 0.1 * i) for i in range(61)]
    probs = [result.exceedance(t) for t in thresholds]
    fig = Figure(
        title="Probability of exceeding an INP concentration (standard dust case)",
        x=Axis("threshold n_INP (per litre)", scale="log10"),
        y=Axis("probability of exceeding", lo=0.0, hi=1.0),
        series=[
            Series(label="P(n_INP > x)", xs=thresholds, ys=probs, colour=PALETTE[0]),
        ],
    )
    fig.caption = (
        "One aerosol mode (1 cm⁻³ at 0.8 µm, σ_g 1.9) at −20 °C, sampled 4000 "
        "times with the parameterization's own uncertainty, ±0.5 K on "
        "temperature, ±30% on number and ±10% on diameter. The curve is shallow "
        "because the answer spans three orders of magnitude, which is the "
        "honest state of this prediction rather than a defect of the sampling. "
        "Roughly 96% of that spread comes from the n_s uncertainty alone — "
        "`ina-sim uncertainty` reports the breakdown, and it is the number that "
        "tells you which measurement is worth improving."
    )
    return figure_block(fig, "Niemand et al. (2012); sampling seeded and reproducible")


def build_figures() -> list[dict[str, Any]]:
    return [
        fig_ns_by_basis("BET"),
        fig_ns_by_basis("geometric"),
        fig_agi_scatter(),
        fig_size_dependence(),
        fig_frozen_fraction(),
        fig_inp_concentration(),
        fig_homogeneous(),
        fig_assay_dynamic_range(),
        fig_exceedance(),
    ]

"""Command-line interface for INA-sim."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from ina_sim import __version__
from ina_sim.library.loader import filter_candidates, load_candidates
from ina_sim.models.conditions import Conditions
from ina_sim.screen.rank import screen_one


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ina-sim",
        description=(
            "Local multi-fidelity ice nucleation agent (INA) screening lab. "
            "v0 is L0/L1 heuristic ranking ported in part from supercool-water-calculator."
        ),
    )
    p.add_argument("--version", action="version", version=f"ina-sim {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List library candidates")

    scr = sub.add_parser("screen", help="Screen/rank candidates under conditions")
    scr.add_argument("--temp", type=float, default=-10.0, help="Temperature °C")
    scr.add_argument("--rh", type=float, default=95.0, help="Relative humidity %%")
    scr.add_argument("--pressure", type=float, default=850.0, help="Pressure hPa")
    scr.add_argument("--volume", type=float, default=1e6, help="Cloud volume m³")
    scr.add_argument("--density", type=float, default=100.0, help="Seeding density particles/L")
    scr.add_argument("--diameter", type=float, default=1.0, help="Particle diameter µm")
    scr.add_argument("--mode", default="immersion", help="immersion|deposition|contact")
    scr.add_argument(
        "--track",
        default="ice",
        choices=["ice", "warm_cloud"],
        help="ice = glaciogenic INA ranking; warm_cloud = hygroscopic/CCN",
    )
    scr.add_argument(
        "--ids",
        nargs="*",
        default=None,
        help="Candidate ids to include (default: all)",
    )
    scr.add_argument(
        "--tag",
        action="append",
        default=None,
        help="Filter by tag (repeatable)",
    )
    scr.add_argument(
        "--sort",
        choices=["relative_ina", "efficiency", "condensable", "ina_per_kg", "cnt_score"],
        default="relative_ina",
    )
    scr.add_argument("--json", action="store_true", help="JSON output")
    scr.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional path to write JSON results",
    )

    ns_p = sub.add_parser(
        "ns",
        help="Evaluate published ns(T) / J(T) parameterizations",
        description=(
            "Ice nucleation active site density ns(T), or nucleation rate "
            "coefficient J(T), straight from the literature. Values outside a "
            "source's fitted temperature range are withheld, not extrapolated."
        ),
    )
    ns_p.add_argument("--temp", type=float, default=-15.0, help="Temperature °C")
    ns_p.add_argument(
        "--id",
        dest="param_id",
        default=None,
        help="Parameterization id (default: all that cover this temperature)",
    )
    ns_p.add_argument(
        "--candidate", default=None, help="Library candidate id instead of a parameterization"
    )
    ns_p.add_argument("--list", action="store_true", help="List the registry and exit")
    ns_p.add_argument(
        "--extrapolate",
        action="store_true",
        help="Return values outside the fitted range, flagged as extrapolated",
    )
    ns_p.add_argument("--json", action="store_true", help="JSON output")

    fz = sub.add_parser(
        "freeze",
        help="Predict droplet-freezing observables (T50, frozen fraction)",
        description=(
            "Convert a parameterization into what a droplet-freezing assay "
            "measures, so predictions can be compared with published data."
        ),
    )
    fz.add_argument("--id", dest="param_id", required=True, help="Parameterization id")
    fz.add_argument(
        "--diameter", type=float, default=1.0, help="Particle diameter µm (default 1.0)"
    )
    fz.add_argument(
        "--curve", action="store_true", help="Print the full freezing curve"
    )
    fz.add_argument("--step", type=float, default=1.0, help="Curve step °C")
    fz.add_argument(
        "--cooling-rate",
        type=float,
        default=1.0,
        help="K/min, used only by rate (stochastic) parameterizations",
    )
    fz.add_argument(
        "--droplet-diameter",
        type=float,
        default=10.0,
        help="Droplet diameter µm, used by volume-based homogeneous freezing",
    )
    fz.add_argument("--json", action="store_true", help="JSON output")

    asy = sub.add_parser(
        "assay",
        help="Import your own droplet-freezing run and invert it to ns(T)",
        description=(
            "Read a cold-stage or microlitre-array experiment (CSV or JSON), "
            "invert it to an ice nucleation active site density spectrum with "
            "droplet-counting uncertainty, and compare it against every "
            "published fit on the same surface-area basis."
        ),
        epilog=(
            "CSV may carry its own metadata as '# key: value' header lines; "
            "flags below override them. Surface area per droplet comes from one "
            "of: --area-m2; --diameter-um with --particles-per-droplet; or "
            "--concentration with --specific-surface-area and --droplet-volume."
        ),
    )
    asy.add_argument("path", help="Path to the experiment file (.csv or .json)")
    asy.add_argument(
        "--area-basis",
        choices=["BET", "geometric"],
        default=None,
        help="Required unless the file states it; decides which fits apply",
    )
    asy.add_argument(
        "--area-m2", type=float, default=None, help="Surface area per droplet, m²"
    )
    asy.add_argument("--diameter-um", type=float, default=None, help="Particle diameter µm")
    asy.add_argument(
        "--particles-per-droplet", type=float, default=None, help="Particles per droplet"
    )
    asy.add_argument(
        "--concentration", type=float, default=None, help="Suspension concentration g/L"
    )
    asy.add_argument(
        "--specific-surface-area",
        type=float,
        default=None,
        help="Specific surface area m²/g (usually BET)",
    )
    asy.add_argument(
        "--droplet-volume", type=float, default=None, help="Droplet volume µL"
    )
    asy.add_argument("--material", default=None, help="What was measured")
    asy.add_argument(
        "--counting",
        choices=["cumulative", "differential"],
        default=None,
        help="Whether the frozen column is cumulative (default) or per-step",
    )
    asy.add_argument(
        "--confidence",
        type=float,
        default=0.95,
        help="Confidence level for counting uncertainty (default 0.95)",
    )
    asy.add_argument(
        "--no-compare",
        action="store_true",
        help="Skip the comparison against published fits",
    )
    asy.add_argument(
        "--out", type=Path, default=None, help="Write the spectrum as CSV to this path"
    )
    asy.add_argument("--json", action="store_true", help="JSON output")

    val = sub.add_parser(
        "validate",
        help="Check this build against published claims",
        description=(
            "Re-derives whether the shipped parameterizations still reproduce "
            "the literature claims in validation/anchors.yaml. Exit code 1 if "
            "any anchor fails."
        ),
    )
    val.add_argument("--json", action="store_true", help="JSON output")

    refs = sub.add_parser("refs", help="Bibliography behind every number")
    refs.add_argument("--key", default=None, help="Show one reference in full")
    refs.add_argument("--json", action="store_true", help="JSON output")

    one = sub.add_parser("show", help="Show one candidate detail + screen at T")
    one.add_argument("id", help="Candidate id")
    one.add_argument("--temp", type=float, default=-10.0)

    gui = sub.add_parser("gui", help="Open minimal local web GUI (table + nucleation sketch)")
    gui.add_argument("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1)")
    gui.add_argument("--port", type=int, default=8765, help="Port (default 8765)")
    gui.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser tab",
    )

    up = sub.add_parser(
        "upload",
        help="Parse a molecular file/SMILES into the session library (builder feed)",
    )
    up.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to .smi/.xyz/.mol/.sdf/.json (or use --smiles)",
    )
    up.add_argument("--smiles", default=None, help="SMILES string instead of file")
    up.add_argument("--name", default=None, help="Display name")
    up.add_argument(
        "--format",
        default=None,
        help="Force format: smiles|xyz|mol|json",
    )
    up.add_argument("--notes", default="", help="Optional notes")
    up.add_argument(
        "--no-persist",
        action="store_true",
        help="Session only (do not write data/uploads/)",
    )

    sub.add_parser("uploads", help="List session / disk-uploaded candidates")

    return p


def _cmd_list() -> int:
    from ina_sim.library.registry import load_persisted

    load_persisted()
    cands = load_candidates(include_uploads=True)
    print(f"{'id':<22} {'class':<14} {'η0':>5} {'Topt':>6}  name")
    print("-" * 80)
    for c in cands:
        print(
            f"{c.id:<22} {c.agent_class.value:<14} "
            f"{c.base_efficiency:>5.2f} {c.optimal_temp_c:>6.1f}  {c.name}"
        )
    print(f"\n{len(cands)} candidates (packaged + uploads)")
    return 0


def _cmd_upload(args: argparse.Namespace) -> int:
    from ina_sim.library.molecular import parse_upload
    from ina_sim.library.registry import load_persisted, register

    load_persisted()
    if args.smiles:
        content = args.smiles
        filename = None
        fmt = args.format or "smiles"
    elif args.path:
        p = Path(args.path)
        content = p.read_text(encoding="utf-8")
        filename = p.name
        fmt = args.format
    else:
        print("Provide a file path or --smiles", file=sys.stderr)
        return 2
    try:
        rec, cand = parse_upload(
            content,
            filename=filename,
            format=fmt,
            name=args.name,
            notes=args.notes,
        )
        register(cand, persist=not args.no_persist)
    except (ValueError, OSError) as e:
        print(f"upload failed: {e}", file=sys.stderr)
        return 1
    print(f"registered {cand.id}")
    print(f"  name:     {cand.name}")
    print(f"  formula:  {cand.formula}")
    print(f"  class:    {cand.agent_class.value}")
    print(f"  η0:       {cand.base_efficiency} (placeholder — exploratory)")
    print(f"  atoms:    {rec.n_atoms}")
    print(f"  format:   {rec.format}")
    if rec.warnings:
        print("  warnings:")
        for w in rec.warnings:
            print(f"    - {w}")
    print("Uncheck Starter set in GUI (or screen without --tag starter-set) to rank it.")
    return 0


def _cmd_uploads() -> int:
    from ina_sim.library.registry import list_session, load_persisted

    load_persisted()
    ups = list_session()
    if not ups:
        print("No uploads in session / data/uploads/")
        return 0
    for c in ups:
        print(f"{c.id:<28} {c.agent_class.value:<14} {c.formula or '—'}  {c.name}")
    print(f"\n{len(ups)} upload(s)")
    return 0


def _cmd_screen(args: argparse.Namespace) -> int:
    from ina_sim.gui.server import run_screen_payload

    ids = list(args.ids) if args.ids else None
    if args.tag and not ids:
        ids = [c.id for c in filter_candidates(tags=args.tag, include_uploads=True)]
        if not ids:
            print("No candidates matched filters.", file=sys.stderr)
            return 1
    starter = bool(args.tag and "starter-set" in args.tag and not args.ids)

    try:
        payload = run_screen_payload(
            temperature_c=args.temp,
            relative_humidity_pct=args.rh,
            pressure_hpa=args.pressure,
            cloud_volume_m3=args.volume,
            seeding_density_per_l=args.density,
            mode=args.mode,
            track=args.track,
            particle_diameter_um=args.diameter,
            starter_set=starter,
            sort_key=args.sort,
            ids=None if starter else ids,
            include_uploads=not starter,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.json or args.out:
        text = json.dumps(payload, indent=2)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
            print(f"Wrote {args.out}")
        if args.json:
            print(text)
            return 0

    c = payload["conditions"]
    print(
        f"INA-sim screen @ T={c['temperature_c']}°C  "
        f"RH={c['relative_humidity_pct']}%  "
        f"P={c['pressure_hpa']} hPa  mode={c['mode']}  track={c.get('track','ice')}  "
        f"baseline=AgI"
    )
    print(payload.get("mechanism_banner", ""))
    print(
        f"{'rank':>4}  {'id':<14}  {'η':>6}  {'relINA':>7}  {'band':>11}  "
        f"{'conf':<12}  source"
    )
    print("-" * 96)
    for i, r in enumerate(payload["results"], 1):
        band = f"{r.get('relative_ina_low', 0):.2f}-{r.get('relative_ina_high', 0):.2f}"
        print(
            f"{i:>4}  {r['id']:<14}  {r['efficiency']:>6.3f}  "
            f"{r['relative_ina']:>7.3f}  {band:>11}  "
            f"{r['confidence']:<12}  {(r.get('source') or '')[:28]}"
        )
    print()
    lit = payload.get("literature_xref", {}).get("summary", {})
    print(
        f"Literature xref: pass={lit.get('pass')} fail={lit.get('fail')} "
        f"ok={lit.get('ok')}  hash={payload.get('provenance', {}).get('param_hash')}"
    )
    print("relINA = η / 0.85 (AgI-class). Bands = confidence uncertainty. Not operational rates.")
    emp = payload.get("empirical_layer") or {}
    summary = emp.get("summary") or {}
    val = emp.get("validation") or {}
    if summary:
        n_solute = summary.get("solute", 0)
        solute_phrase = (
            f"{n_solute} is a soluble salt with no ns(T) at all"
            if n_solute == 1
            else f"{n_solute} are soluble salts with no ns(T) at all"
        )
        print(
            f"Evidence: {summary.get('measured', 0)}/{summary.get('n_candidates', 0)} "
            f"candidates have a parameterization, "
            f"{summary.get('with_value_at_this_temperature', 0)} return a value at "
            f"this temperature, {solute_phrase}.  "
            f"Validation: {val.get('pass', '?')} passed / "
            f"{val.get('fail', '?')} failed.  `ina-sim ns --temp "
            f"{c['temperature_c']:g}` for the numbers."
        )
    if payload.get("clamped"):
        print("NOTE: some inputs were clamped into the lab envelope.")
    warns = payload.get("warnings") or []
    if warns:
        print("Warnings:")
        for w in warns:
            print(f"  - {w}")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    from ina_sim.library.loader import get_candidate

    try:
        c = get_candidate(args.id)
    except KeyError as e:
        print(str(e), file=sys.stderr)
        return 1
    conditions = Conditions(temperature_c=args.temp)
    r = screen_one(c, conditions)
    print(f"{c.name} ({c.id})")
    print(f"  class:        {c.agent_class.value}")
    print(f"  formula:      {c.formula}")
    print(f"  base η:       {c.base_efficiency}")
    print(f"  T_opt °C:     {c.optimal_temp_c}")
    print(f"  lattice:      {c.lattice_match_score}")
    print(f"  density:      {c.density_g_cm3} g/cm³")
    print(f"  source:       {c.source}")
    print(f"  notes:        {c.notes}")
    print(f"  tags:         {', '.join(c.tags)}")
    print(f"@ {args.temp}°C:")
    print(f"  efficiency:   {r.overall_efficiency:.4f} ({r.efficiency_rating})")
    print(f"  relative INA: {r.relative_ina_score:.4f}")
    print(f"  INA/kg proxy: {r.ina_per_kg_proxy}")
    print(f"  confidence:   {r.confidence.value}")
    if r.warnings:
        print("  warnings:")
        for w in r.warnings:
            print(f"    - {w}")
    return 0


def _cmd_ns(args: argparse.Namespace) -> int:
    from ina_sim.physics.ns import (
        evaluate,
        evaluate_for_candidate,
        get_parameterization,
        load_parameterizations,
        registry_summary,
    )

    if args.list:
        summary = registry_summary()
        if args.json:
            print(json.dumps(summary, indent=2))
            return 0
        print(
            f"{summary['count']} parameterizations "
            f"({summary['published']} published, {summary['derived']} derived in-repo)"
        )
        print(f"{'id':<32} {'basis':<10} {'valid T °C':>14}  {'σ':>5}  citation")
        print("-" * 100)
        for p in summary["parameterizations"]:
            lo, hi = p["valid_t_c"]
            sigma = "—" if p["sigma_log10"] is None else f"{p['sigma_log10']:.2f}"
            print(
                f"{p['id']:<32} {p['area_basis']:<10} "
                f"{lo:>6.1f}..{hi:<6.1f} {sigma:>5}  {p['citation']}"
            )
        return 0

    if args.candidate:
        est = evaluate_for_candidate(
            args.candidate, args.temp, allow_extrapolation=args.extrapolate
        )
        if est is None:
            print(
                f"No parameterization covers {args.candidate!r}. That is a real "
                "answer: nothing in the literature this build carries measures it.",
                file=sys.stderr,
            )
            return 1
        estimates = [est]
    elif args.param_id:
        try:
            estimates = [
                evaluate(
                    get_parameterization(args.param_id),
                    args.temp,
                    allow_extrapolation=args.extrapolate,
                )
            ]
        except KeyError as e:
            print(str(e), file=sys.stderr)
            return 1
    else:
        estimates = [
            evaluate(p, args.temp, allow_extrapolation=args.extrapolate)
            for p in load_parameterizations().values()
        ]

    if args.json:
        print(json.dumps([e.as_dict() for e in estimates], indent=2))
        return 0

    print(f"T = {args.temp:g} °C")
    header = (
        f"{'parameterization':<32} {'quantity':<8} {'value':>12} "
        f"{'units':<11} {'basis':<10} status"
    )
    print(header)
    print("-" * 100)
    for est in sorted(estimates, key=lambda x: (x.value is None, -(x.value or 0.0))):
        if est.value is None:
            value, status = "—", "outside fitted range"
        else:
            value = f"{est.value:.3e}"
            assumed = " (assumed)" if est.sigma_assumed else ""
            status = f"±{est.sigma_log10:.2g} dec{assumed}"
            if est.extrapolated:
                status += " EXTRAPOLATED"
        print(
            f"{est.parameterization_id:<32} {est.quantity:<8} {value:>12} "
            f"{est.units:<11} {est.area_basis:<10} {status}"
        )
    print()
    print(
        "ns values on different area bases (BET vs geometric) are not "
        "comparable; rate coefficients are not densities at all."
    )
    for est in estimates:
        for note in est.notes:
            print(f"  [{est.parameterization_id}] {note}")
    return 0


def _cmd_freeze(args: argparse.Namespace) -> int:
    from ina_sim.physics.freezing import (
        freezing_curve,
        median_freezing_temperature,
        stochastic_freezing_curve,
    )
    from ina_sim.physics.ns import get_parameterization
    from ina_sim.units import (
        micrometres_to_metres,
        sphere_surface_area_m2,
        sphere_volume_m3,
    )

    try:
        param = get_parameterization(args.param_id)
    except KeyError as e:
        print(str(e), file=sys.stderr)
        return 1

    area_m2 = sphere_surface_area_m2(micrometres_to_metres(args.diameter))

    if param.quantity == "ns":
        t50 = median_freezing_temperature(param, area_m2)
        curve = (
            freezing_curve(param, droplet_surface_area_m2=area_m2, step_c=args.step)
            if args.curve
            else []
        )
        payload = {
            "parameterization": param.id,
            "material": param.material,
            "description": "singular (time independent)",
            "particle_diameter_um": args.diameter,
            "particle_surface_area_m2": area_m2,
            "t50_c": t50,
            "curve": [p.as_dict() for p in curve],
            "citation": param.as_dict()["citation"],
        }
    else:
        volume_m3 = sphere_volume_m3(micrometres_to_metres(args.droplet_diameter))
        is_hom = param.area_basis == "volume"
        curve_rows = stochastic_freezing_curve(
            None if is_hom else param,
            particle_area_m2=0.0 if is_hom else area_m2,
            droplet_volume_m3=volume_m3,
            hom_param=param if is_hom else None,
            cooling_rate_k_per_min=args.cooling_rate,
            t_start_c=param.t_max_c,
            t_end_c=param.t_min_c,
            step_c=min(args.step, 0.05),
        )
        t50 = next((r["T_c"] for r in curve_rows if r["frozen_fraction"] >= 0.5), None)
        payload = {
            "parameterization": param.id,
            "material": param.material,
            "description": f"stochastic (rate), cooling {args.cooling_rate} K/min",
            "particle_diameter_um": None if is_hom else args.diameter,
            "droplet_diameter_um": args.droplet_diameter,
            "t50_c": t50,
            "curve": curve_rows if args.curve else [],
            "citation": param.as_dict()["citation"],
        }

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"{param.material}  [{param.id}]")
    print(f"  description:  {payload['description']}")
    print(f"  citation:     {payload['citation']}")
    print(f"  valid range:  {param.t_min_c:g} .. {param.t_max_c:g} °C")
    if payload.get("particle_diameter_um"):
        print(f"  particle:     {args.diameter:g} µm sphere, area {area_m2:.3e} m²")
    if param.quantity != "ns":
        print(f"  droplet:      {args.droplet_diameter:g} µm")
    if payload["t50_c"] is None:
        print("  T50:          not reached inside the fitted range")
    else:
        print(f"  T50:          {payload['t50_c']:.2f} °C (half of droplets frozen)")
    if args.curve:
        print()
        print(f"{'T °C':>8}  frozen fraction")
        for row in payload["curve"]:
            frozen = row["frozen_fraction"]
            bar = "#" * int(round(frozen * 40))
            print(f"{row['T_c']:>8.2f}  {frozen:>6.3f} {bar}")
    return 0


def _cmd_assay(args: argparse.Namespace) -> int:
    from ina_sim.assay import (
        AssayError,
        build_spectrum,
        compare_to_registry,
        load_assay,
    )

    overrides = {
        "area_basis": args.area_basis,
        "surface_area_m2_per_droplet": args.area_m2,
        "particle_diameter_um": args.diameter_um,
        "particles_per_droplet": args.particles_per_droplet,
        "concentration_g_per_l": args.concentration,
        "specific_surface_area_m2_per_g": args.specific_surface_area,
        "droplet_volume_ul": args.droplet_volume,
        "material": args.material,
        "counting": args.counting,
    }
    try:
        assay = load_assay(args.path, overrides=overrides)
        spectrum = build_spectrum(assay, confidence=args.confidence)
    except AssayError as exc:
        print(f"Could not read the experiment: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    comparisons = [] if args.no_compare else compare_to_registry(spectrum)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(spectrum.to_csv(), encoding="utf-8")
        if not args.json:
            print(f"Wrote spectrum to {args.out}")

    if args.json:
        payload = spectrum.as_dict()
        payload["comparisons"] = [c.as_dict() for c in comparisons]
        print(json.dumps(payload, indent=2))
        return 0

    meta = spectrum.metadata
    print(f"{meta.get('material') or 'unnamed sample'}  [{spectrum.source_path}]")
    print(f"  sha256:       {spectrum.source_sha256}")
    print(f"  droplet area: {spectrum.area_m2:.4g} m²  ({spectrum.area_route})")
    print(f"  area basis:   {spectrum.area_basis}")
    print(
        f"  resolvable:   ns {spectrum.ns_resolvable_min_m2:.3g} … "
        f"{spectrum.ns_resolvable_max_m2:.3g} m⁻²  "
        f"(set by the number of droplets)"
    )
    t50 = spectrum.t50_c()
    print(f"  measured T50: {'—' if t50 is None else f'{t50:.2f} °C'}")
    span = spectrum.temperature_span_c()
    print(
        f"  usable:       {len(spectrum.usable)}/{len(spectrum.points)} points"
        + (f", {span[0]:.1f} … {span[1]:.1f} °C" if span else "")
    )
    print()
    print(f"{'T °C':>7}  {'frozen':>9}  {'f':>6}  {'log10 ns':>9}  {'band':>15}  note")
    print("-" * 92)
    for p in spectrum.points:
        frozen = f"{p.n_frozen}/{p.n_total}"
        if p.log10_ns is None:
            value, band = "—", ""
        else:
            value = f"{p.log10_ns:.2f}"
            lo = "—" if not p.ns_low_m2 else f"{math.log10(p.ns_low_m2):.2f}"
            hi = "—" if not p.ns_high_m2 else f"{math.log10(p.ns_high_m2):.2f}"
            band = f"{lo} … {hi}"
        flag = ""
        if p.limit == "upper":
            flag = "upper limit only"
        elif p.limit == "lower":
            flag = "saturated (lower limit)"
        elif not p.within_dynamic_range:
            flag = "outside resolvable window"
        print(
            f"{p.temperature_c:>7.2f}  {frozen:>9}  {p.frozen_fraction:>6.2f}  "
            f"{value:>9}  {band:>15}  {flag}"
        )
    print()
    print(
        f"Bands are droplet-counting uncertainty at {spectrum.confidence:.0%} "
        "(Wilson score interval). Temperature calibration and surface-area "
        "uncertainty are NOT included and are usually larger."
    )

    if comparisons:
        print()
        print(f"Against published fits on the same ({spectrum.area_basis}) area basis:")
        print(f"{'parameterization':<32} {'n':>4} {'bias':>7} {'rmse':>6} {'cover':>6}  verdict")
        print("-" * 100)
        for c in comparisons:
            if c.n_compared == 0:
                print(f"{c.parameterization_id:<32} {0:>4} {'—':>7} {'—':>6} {'—':>6}  {c.verdict}")
                continue
            print(
                f"{c.parameterization_id:<32} {c.n_compared:>4} "
                f"{c.bias_log10:>+7.2f} {c.rmse_log10:>6.2f} "
                f"{c.coverage_fraction:>6.0%}  {c.verdict}"
            )
        print()
        print(
            "bias and rmse are in decades of log10(ns); cover is the fraction of "
            "measured points inside that fit's own 1σ band. Fits on a different "
            "area basis are excluded, not silently compared."
        )
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    from ina_sim.validation.runner import format_report, run_validation

    report = run_validation()
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(format_report(report))
    return 0 if report.ok else 1


def _cmd_refs(args: argparse.Namespace) -> int:
    from ina_sim.references import get_reference, load_references

    refs = load_references()
    if args.key:
        try:
            ref = get_reference(args.key)
        except KeyError as e:
            print(str(e), file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps({**ref.as_dict(), "note": ref.note}, indent=2))
            return 0
        print(ref.citation())
        print(f"  access:      {ref.access}")
        print(f"  open access: {ref.open_access}")
        if ref.url:
            print(f"  url:         {ref.url}")
        if ref.note:
            print(f"  note:        {' '.join(ref.note.split())}")
        return 0

    if args.json:
        print(json.dumps([r.as_dict() for r in refs.values()], indent=2))
        return 0
    print(f"{len(refs)} references")
    for key, ref in refs.items():
        flag = "open" if ref.open_access else "paywalled"
        print(f"  {key:<16} {ref.short():<32} {ref.access:<9} {flag}")
        if ref.doi:
            print(f"  {'':<16} doi:{ref.doi}")
    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    from ina_sim.gui.server import run_gui

    run_gui(host=args.host, port=args.port, open_browser=not args.no_browser)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "list":
        return _cmd_list()
    if args.cmd == "screen":
        return _cmd_screen(args)
    if args.cmd == "show":
        return _cmd_show(args)
    if args.cmd == "ns":
        return _cmd_ns(args)
    if args.cmd == "assay":
        return _cmd_assay(args)
    if args.cmd == "freeze":
        return _cmd_freeze(args)
    if args.cmd == "validate":
        return _cmd_validate(args)
    if args.cmd == "refs":
        return _cmd_refs(args)
    if args.cmd == "gui":
        return _cmd_gui(args)
    if args.cmd == "upload":
        return _cmd_upload(args)
    if args.cmd == "uploads":
        return _cmd_uploads()
    parser.error(f"unknown command {args.cmd}")
    return 2

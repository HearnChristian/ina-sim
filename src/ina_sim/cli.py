"""Command-line interface for INA-sim."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ina_sim import __version__
from ina_sim.library.loader import filter_candidates, load_candidates
from ina_sim.models.conditions import Conditions
from ina_sim.screen.rank import rank_candidates, screen_one


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
    from ina_sim.library.loader import filter_candidates

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
    if args.cmd == "gui":
        return _cmd_gui(args)
    if args.cmd == "upload":
        return _cmd_upload(args)
    if args.cmd == "uploads":
        return _cmd_uploads()
    parser.error(f"unknown command {args.cmd}")
    return 2

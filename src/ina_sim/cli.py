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
    scr.add_argument("--rh", type=float, default=95.0, help="Relative humidity %")
    scr.add_argument("--pressure", type=float, default=850.0, help="Pressure hPa")
    scr.add_argument("--volume", type=float, default=1e6, help="Cloud volume m³")
    scr.add_argument("--density", type=float, default=100.0, help="Seeding density particles/L")
    scr.add_argument("--mode", default="immersion", help="immersion|deposition|contact")
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
        choices=["relative_ina", "efficiency", "condensable", "ina_per_kg"],
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

    return p


def _cmd_list() -> int:
    cands = load_candidates()
    print(f"{'id':<16} {'class':<14} {'η0':>5} {'Topt':>6}  name")
    print("-" * 72)
    for c in cands:
        print(
            f"{c.id:<16} {c.agent_class.value:<14} "
            f"{c.base_efficiency:>5.2f} {c.optimal_temp_c:>6.1f}  {c.name}"
        )
    print(f"\n{len(cands)} candidates")
    return 0


def _cmd_screen(args: argparse.Namespace) -> int:
    conditions = Conditions(
        temperature_c=args.temp,
        relative_humidity_pct=args.rh,
        pressure_hpa=args.pressure,
        cloud_volume_m3=args.volume,
        seeding_density_per_l=args.density,
        mode=args.mode,
    )
    cands = filter_candidates(ids=args.ids, tags=args.tag)
    if not cands:
        print("No candidates matched filters.", file=sys.stderr)
        return 1
    ranked = rank_candidates(cands, conditions, sort_key=args.sort)
    rows = [r.as_row() for r in ranked]

    if args.json or args.out:
        payload = {
            "version": __version__,
            "fidelity": "L0+L1-heuristic",
            "disclaimer": (
                "Heuristic ranking for R&D decision-support. Not operational "
                "weather-modification guidance. INA/kg is assumption-dependent."
            ),
            "conditions": {
                "temperature_c": conditions.temperature_c,
                "relative_humidity_pct": conditions.relative_humidity_pct,
                "pressure_hpa": conditions.pressure_hpa,
                "cloud_volume_m3": conditions.cloud_volume_m3,
                "seeding_density_per_l": conditions.seeding_density_per_l,
                "mode": conditions.mode,
            },
            "results": rows,
        }
        text = json.dumps(payload, indent=2)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
            print(f"Wrote {args.out}")
        if args.json:
            print(text)
            return 0

    print(
        f"INA-sim screen @ T={conditions.temperature_c}°C  "
        f"RH={conditions.relative_humidity_pct}%  "
        f"P={conditions.pressure_hpa} hPa  mode={conditions.mode}"
    )
    print(
        f"{'rank':>4}  {'id':<14}  {'η':>6}  {'relINA':>7}  "
        f"{'INA/kg*':>8}  {'conf':<12}  name"
    )
    print("-" * 88)
    for i, r in enumerate(ranked, 1):
        ina = "—" if r.ina_per_kg_proxy is None else f"{r.ina_per_kg_proxy:8.3f}"
        print(
            f"{i:>4}  {r.candidate.id:<14}  {r.overall_efficiency:>6.3f}  "
            f"{r.relative_ina_score:>7.3f}  {ina:>8}  "
            f"{r.confidence.value:<12}  {r.candidate.name}"
        )
    print()
    print("* ina_per_kg_proxy is relative to AgI-like reference under fixed particle assumptions.")
    print("  Fidelity: L0+L1-heuristic (not MD/CNT absolute rates).")
    warns = sorted({w for r in ranked for w in r.warnings})
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


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "list":
        return _cmd_list()
    if args.cmd == "screen":
        return _cmd_screen(args)
    if args.cmd == "show":
        return _cmd_show(args)
    parser.error(f"unknown command {args.cmd}")
    return 2

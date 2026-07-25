"""Empirical claim extraction from a screen result set.

Goal: surface what the *current run* supports as a claim, what is provisional,
and what is not warranted — so the user can discover claim boundaries from data,
not from marketing copy.
"""

from __future__ import annotations

from typing import Any, Sequence


def _idx(ids: Sequence[str], cid: str) -> int | None:
    try:
        return list(ids).index(cid)
    except ValueError:
        return None


def extract_claims(
    *,
    ranked_ids: Sequence[str],
    scores: dict[str, float],
    temperature_c: float,
    mode: str,
    track: str,
    literature_ok: bool,
    literature_fails: Sequence[str],
) -> dict[str, Any]:
    """Return structured claim tiers for this screen only."""
    supported: list[dict[str, str]] = []
    provisional: list[dict[str, str]] = []
    not_warranted: list[dict[str, str]] = []

    # Scale / normalization claims
    if "agi" in scores:
        s_agi = scores["agi"]
        if abs(temperature_c - (-7.0)) <= 1.5 and s_agi >= 0.9:
            supported.append(
                {
                    "id": "agi_near_peak",
                    "claim": (
                        f"At T≈{temperature_c}°C (near AgI table peak), AgI relative score "
                        f"is {s_agi:.2f} ≈ 1 on the model’s 0–1 AgI-peak scale."
                    ),
                    "basis": "activity table peak × peak_strength=1 for AgI",
                }
            )
        elif s_agi > 1.001:
            not_warranted.append(
                {
                    "id": "score_exceeds_unity",
                    "claim": f"AgI score {s_agi:.3f} > 1 — scale bug; do not claim.",
                    "basis": "scores must lie in [0,1]",
                }
            )

    # Ordering claims (ice track immersion)
    if track == "ice" and mode == "immersion":
        pairs = [
            ("agi", "water_control", "AgI outranks pure-water control"),
            ("agi", "inert_surface", "AgI outranks inert surface control"),
            ("k_feldspar", "kaolinite", "K-feldspar outranks kaolinite"),
            ("agi", "nacl", "AgI outranks sea-salt (CCN) on ice track"),
            ("k_feldspar", "nacl", "K-feldspar outranks sea-salt on ice track"),
        ]
        for better, worse, text in pairs:
            ib, iw = _idx(ranked_ids, better), _idx(ranked_ids, worse)
            if ib is None or iw is None:
                continue
            sb, sw = scores.get(better), scores.get(worse)
            if ib < iw and sb is not None and sw is not None and sb > sw:
                entry = {
                    "id": f"order_{better}_gt_{worse}",
                    "claim": (
                        f"{text} at T={temperature_c}°C immersion "
                        f"({better}={sb:.2f} > {worse}={sw:.2f})."
                    ),
                    "basis": "model ranking under stated assumptions + activity tables",
                }
                # Align with literature xref when relevant
                weaker = ("kaolinite", "nacl", "water_control")
                if better in ("k_feldspar", "agi") and worse in weaker:
                    if literature_ok:
                        supported.append(entry)
                    else:
                        provisional.append(
                            {
                                **entry,
                                "basis": entry["basis"]
                                + "; literature_xref failed: "
                                + (", ".join(literature_fails) or "see checks"),
                            }
                        )
                else:
                    supported.append(entry)
            elif ib > iw:
                not_warranted.append(
                    {
                        "id": f"order_fail_{better}_gt_{worse}",
                        "claim": (
                            f"Cannot claim {text} at T={temperature_c}°C — "
                            f"model ranks {worse} above {better}."
                        ),
                        "basis": "this run’s ordering",
                    }
                )

    # Mode / track caveats as explicit non-claims when conditions wrong
    if mode == "deposition":
        provisional.append(
            {
                "id": "deposition_mode",
                "claim": (
                    "Deposition-mode scores require ice supersaturation; "
                    "interpret only with atmosphere S_ice > 1."
                ),
                "basis": "deposition pathway physics",
            }
        )
    if track == "warm_cloud":
        supported.append(
            {
                "id": "warm_track_scope",
                "claim": (
                    "This run ranks liquid-drop (CCN) pathways; ice-nucleant order is "
                    "intentionally demoted and should not be used as an INA ranking."
                ),
                "basis": "track=warm_cloud design",
            }
        )

    # Absolute rate / field claims — always not warranted from this tool alone
    not_warranted.extend(
        [
            {
                "id": "no_absolute_ns",
                "claim": "Absolute ice-nucleating particle concentration ns(T) (#/L).",
                "basis": "model has no lab-calibrated INP transfer function",
            },
            {
                "id": "no_radar_precip",
                "claim": "Precipitation amount or radar verification from seeding.",
                "basis": "no cloud-resolving / dynamical coupling",
            },
            {
                "id": "no_ops_dose",
                "claim": "Operational seeding dose (g/km) for a campaign.",
                "basis": "requires aircraft, meteorology, and regulatory context",
            },
        ]
    )

    if literature_fails:
        provisional.append(
            {
                "id": "lit_xref_attention",
                "claim": (
                    "Literature cross-check reported failures — treat ranking claims "
                    f"as provisional until resolved: {', '.join(literature_fails)}."
                ),
                "basis": "literature_xref",
            }
        )

    return {
        "temperature_c": temperature_c,
        "mode": mode,
        "track": track,
        "supported": supported,
        "provisional": provisional,
        "not_warranted_by_this_run": not_warranted,
        "summary": {
            "n_supported": len(supported),
            "n_provisional": len(provisional),
            "n_not_warranted": len(not_warranted),
        },
        "note": (
            "Claims are inferred from this screen’s scores and literature_xref. "
            "Supported = warranted under model assumptions; provisional = weak or "
            "contested; not_warranted = outside tool scope or contradicted by this run."
        ),
    }

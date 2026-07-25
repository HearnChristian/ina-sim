"""Cross-reference screening results against public research *direction*.

These checks encode widely cited atmospheric / ice-nucleation facts so the
learning lab fails closed if rankings invert known science. They do **not**
validate absolute nucleation rates or field seeding performance.

Primary literature flavors (teaching anchors, not full citations DB):

- Saturation vapor pressure tables / Magnus family (e.g. Alduchov & Eskridge;
  common met textbooks; Lide handbook ~6.11 hPa at 0 °C).
- Ice vs supercooled water vapor pressure (mixed-phase / Bergeron process context).
- Homogeneous freezing of pure water droplets ~ −35 to −38 °C
  (Pruppacher & Klett / cloud physics texts).
- Silver iodide as classic glaciogenic seeding agent (Vonnegut-era lineage;
  operational cloud-seeding reviews: effective in cold mixed-phase).
- K-feldspar as highly ice-active mineral dust component
  (Atkinson et al., Nature 2013 and follow-on immersion IN studies).
- Kaolinite / clays typically less active / colder than K-feldspar
  (comparative mineral IN literature, e.g. Zolles et al. and reviews).
- Sea salt primarily CCN / hygroscopic, not a leading atmospheric INA
  (standard aerosol–cloud teaching contrast).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from ina_sim.physics.atmosphere import (
    atmosphere_state,
    saturating_vapor_pressure_hpa,
    saturating_vapor_pressure_ice_hpa,
)


@dataclass(frozen=True)
class XrefCheck:
    id: str
    status: str  # pass | fail | skip
    detail: str
    refs: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "status": self.status,
            "detail": self.detail,
            "refs": self.refs,
        }


def _rank_index(ids: Sequence[str], cand_id: str) -> int | None:
    try:
        return list(ids).index(cand_id)
    except ValueError:
        return None


def _passes_order(ids: Sequence[str], better: str, worse: str) -> bool | None:
    ib, iw = _rank_index(ids, better), _rank_index(ids, worse)
    if ib is None or iw is None:
        return None
    return ib < iw


def check_atmosphere(temp_c: float, rh: float, pressure_hpa: float) -> list[XrefCheck]:
    out: list[XrefCheck] = []
    e0 = saturating_vapor_pressure_hpa(0.0)
    ok = 6.0 < e0 < 6.25
    out.append(
        XrefCheck(
            "es_water_0C",
            "pass" if ok else "fail",
            f"e_s,w(0°C)={e0:.3f} hPa (expect ~6.11 ±2%)",
            "Lide / IAPWS neighborhood; August–Roche–Magnus",
        )
    )
    if temp_c < 0:
        ew = saturating_vapor_pressure_hpa(temp_c)
        ei = saturating_vapor_pressure_ice_hpa(temp_c)
        ok_ice = ei < ew
        out.append(
            XrefCheck(
                "ice_es_lt_water",
                "pass" if ok_ice else "fail",
                f"e_s,ice={ei:.3f} < e_s,w={ew:.3f} at T={temp_c}°C",
                "Supercooled liquid metastable vs ice (cloud physics)",
            )
        )
        atm = atmosphere_state(temp_c, rh, pressure_hpa)
        ok_rh = atm.rh_ice_pct > atm.relative_humidity_pct - 1e-6
        out.append(
            XrefCheck(
                "rh_ice_gt_rh_water",
                "pass" if ok_rh else "fail",
                f"RH_ice={atm.rh_ice_pct:.1f}% vs RH_w={rh}%",
                "Definition RH_i = e/e_s,i; Bergeron/mixed-phase context",
            )
        )
    else:
        out.append(
            XrefCheck(
                "ice_es_lt_water",
                "skip",
                "T≥0 — ice/water supercooled comparison skipped",
                "N/A above 0 °C",
            )
        )
    return out


def check_ranking(
    ranked_ids: Sequence[str],
    *,
    temp_c: float,
    mode: str,
    agent_classes: dict[str, str] | None = None,
) -> list[XrefCheck]:
    """Directional ranking checks for mixed-phase immersion-like screens."""
    out: list[XrefCheck] = []
    ids = list(ranked_ids)
    mode = (mode or "immersion").lower()

    # Controls must be weak
    for ctrl in ("water_control", "inert_surface"):
        for good in ("agi", "k_feldspar"):
            ord_ = _passes_order(ids, good, ctrl)
            if ord_ is None:
                continue
            out.append(
                XrefCheck(
                    f"{good}_beats_{ctrl}",
                    "pass" if ord_ else "fail",
                    f"{good} rank vs {ctrl} at T={temp_c}°C mode={mode}",
                    "Glaciogenic / mineral INA ≫ homogeneous or inert controls",
                )
            )

    # Feldspar vs kaolinite in mixed-phase immersion
    if mode == "immersion" and -25.0 <= temp_c <= -5.0:
        ord_ = _passes_order(ids, "k_feldspar", "kaolinite")
        if ord_ is not None:
            out.append(
                XrefCheck(
                    "feldspar_gt_kaolinite",
                    "pass" if ord_ else "fail",
                    f"k_feldspar vs kaolinite at T={temp_c}°C (expect feldspar more active)",
                    "Atkinson et al. Nature 2013 lineage; mineral immersion IN comparisons",
                )
            )

    # Sea salt not top ice agent when cold immersion
    if mode == "immersion" and temp_c <= -10.0:
        for good in ("agi", "k_feldspar"):
            ord_ = _passes_order(ids, good, "nacl")
            if ord_ is None:
                continue
            out.append(
                XrefCheck(
                    f"{good}_beats_nacl_cold",
                    "pass" if ord_ else "fail",
                    f"{good} should outrank nacl (CCN) at T={temp_c}°C immersion",
                    "Sea salt primarily CCN; not leading atmospheric INA",
                )
            )

    # AgI should be competitive in classic seeding window
    if mode == "immersion" and -15.0 <= temp_c <= -5.0:
        ia = _rank_index(ids, "agi")
        if ia is not None:
            # top half of library is enough for teaching model
            ok = ia <= max(2, len(ids) // 2)
            out.append(
                XrefCheck(
                    "agi_competitive_mixed_phase",
                    "pass" if ok else "fail",
                    f"agi rank index {ia}/{len(ids)} at T={temp_c}°C (expect competitive)",
                    "AgI classic glaciogenic seeding agent (mixed-phase cold clouds)",
                )
            )

    # Hygroscopic should not silently claim ice_nucleation pathway
    if agent_classes:
        for cid, cls in agent_classes.items():
            if cls == "hygroscopic" and cid in ids:
                out.append(
                    XrefCheck(
                        f"hygroscopic_class_{cid}",
                        "pass",
                        f"{cid} labeled agent_class=hygroscopic (CCN path, not INA)",
                        "Mechanism distinction: CCN vs ice nucleant",
                    )
                )
                break

    return out


def cross_reference_screen(
    *,
    ranked_ids: Sequence[str],
    temperature_c: float,
    relative_humidity_pct: float,
    pressure_hpa: float,
    mode: str,
    agent_classes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build literature_xref block for API / CLI."""
    checks = check_atmosphere(temperature_c, relative_humidity_pct, pressure_hpa)
    checks.extend(
        check_ranking(
            ranked_ids,
            temp_c=temperature_c,
            mode=mode,
            agent_classes=agent_classes,
        )
    )
    n_pass = sum(1 for c in checks if c.status == "pass")
    n_fail = sum(1 for c in checks if c.status == "fail")
    n_skip = sum(1 for c in checks if c.status == "skip")
    return {
        "summary": {
            "pass": n_pass,
            "fail": n_fail,
            "skip": n_skip,
            "ok": n_fail == 0,
        },
        "checks": [c.as_dict() for c in checks],
        "disclaimer": (
            "Directional consistency with public atmospheric / IN literature. "
            "Not a calibration to measured ns(T) or operational seeding rates."
        ),
    }

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ina_sim.models.candidate import Candidate, Confidence
from ina_sim.models.conditions import Conditions


@dataclass
class ScreenResult:
    """One candidate evaluated under one set of conditions."""

    candidate: Candidate
    conditions: Conditions
    overall_efficiency: float
    efficiency_rating: str
    temp_efficiency_factor: float
    density_efficiency_factor: float
    total_water_vapor_kg: float
    condensable_water_kg: float
    relative_ina_score: float
    relative_ina_low: float
    relative_ina_high: float
    ina_per_kg_proxy: float | None
    confidence: Confidence
    fidelity: str = "L0+L1-table+CNT"
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def as_row(self) -> dict[str, Any]:
        return {
            "id": self.candidate.id,
            "name": self.candidate.name,
            "class": self.candidate.agent_class.value,
            "efficiency": round(self.overall_efficiency, 4),
            "rating": self.efficiency_rating,
            "relative_ina": round(self.relative_ina_score, 4),
            "relative_ina_low": round(self.relative_ina_low, 4),
            "relative_ina_high": round(self.relative_ina_high, 4),
            "ina_per_kg_proxy": (
                None
                if self.ina_per_kg_proxy is None
                else round(self.ina_per_kg_proxy, 4)
            ),
            "condensable_kg": round(self.condensable_water_kg, 3),
            "confidence": self.confidence.value,
            "fidelity": self.fidelity,
            "T_c": self.conditions.temperature_c,
            "pathway": self.details.get("pathway"),
            "mode_factor": self.details.get("mode_factor"),
            "cnt_score": self.details.get("cnt_score"),
            "temp_method": self.details.get("temp_method"),
            "source": self.details.get("source"),
            "citation": self.details.get("citation"),
            "cnt": self.details.get("cnt"),
            # Empirical layer: what is measured for this material, if anything.
            # Additive by design so existing consumers keep working unchanged.
            "evidence": self.details.get("evidence"),
            "ns_m2": ((self.details.get("evidence") or {}).get("ns") or {}).get("value"),
            "ns_units": ((self.details.get("evidence") or {}).get("ns") or {}).get("units"),
            "ns_citation": (
                ((self.details.get("evidence") or {}).get("ns") or {}).get("citation")
            ),
            # Size and dose: these respond to the particle diameter and seeding
            # density inputs, which the relative score deliberately does not.
            "activation": self.details.get("activation"),
            "activation_probability": (
                (self.details.get("activation") or {}).get("activation_probability")
            ),
            "n_inp_per_litre": (
                (self.details.get("activation") or {}).get("n_inp_per_litre")
            ),
            "warnings": "; ".join(self.warnings) if self.warnings else "",
        }

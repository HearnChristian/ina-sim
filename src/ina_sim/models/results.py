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
    # Bridged engineering proxies (assumption-dependent)
    relative_ina_score: float
    ina_per_kg_proxy: float | None
    confidence: Confidence
    fidelity: str = "L0+L1-heuristic"
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
            "ina_per_kg_proxy": (
                None
                if self.ina_per_kg_proxy is None
                else round(self.ina_per_kg_proxy, 4)
            ),
            "condensable_kg": round(self.condensable_water_kg, 3),
            "confidence": self.confidence.value,
            "fidelity": self.fidelity,
            "T_c": self.conditions.temperature_c,
            "warnings": "; ".join(self.warnings) if self.warnings else "",
        }

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Confidence(str, Enum):
    """How much trust to put in a ranked result for this candidate class."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    EXPLORATORY = "exploratory"


class AgentClass(str, Enum):
    ICE_NUCLEANT = "ice_nucleant"  # e.g. AgI, feldspar
    HYGROSCOPIC = "hygroscopic"  # e.g. NaCl warm/glaciogenic-adjacent
    ORGANIC = "organic"
    CONTROL = "control"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Candidate:
    """Library entry for an ice-nucleating or seeding agent."""

    id: str
    name: str
    formula: str | None = None
    agent_class: AgentClass = AgentClass.UNKNOWN
    # Heuristic fields (from supercool calculator + extensions)
    base_efficiency: float = 0.5
    optimal_temp_c: float = -10.0
    # Optional literature / descriptor hooks
    lattice_match_score: float | None = None  # 0–1 proxy vs ice Ih
    density_g_cm3: float | None = None
    notes: str = ""
    source: str = "library"
    tags: tuple[str, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)

    def default_confidence(self) -> Confidence:
        if self.agent_class == AgentClass.CONTROL:
            return Confidence.HIGH
        if self.id in {"agi", "k_feldspar", "kaolinite", "water_control"}:
            return Confidence.HIGH
        if self.agent_class == AgentClass.ICE_NUCLEANT:
            return Confidence.MEDIUM
        if self.agent_class == AgentClass.HYGROSCOPIC:
            return Confidence.MEDIUM
        if self.agent_class == AgentClass.ORGANIC:
            return Confidence.EXPLORATORY
        return Confidence.LOW

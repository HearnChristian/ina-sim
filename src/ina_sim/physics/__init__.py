"""Physics helpers.

Atmospheric vapor inventory and agent-efficiency heuristics were ported from
HearnChristian/supercool-water-calculator (legacy HTML), then expanded.
"""

from ina_sim.physics.atmosphere import (
    air_density_kg_m3,
    saturating_vapor_pressure_hpa,
    specific_humidity,
    total_water_vapor_kg,
)
from ina_sim.physics.efficiency import agent_efficiency

__all__ = [
    "air_density_kg_m3",
    "saturating_vapor_pressure_hpa",
    "specific_humidity",
    "total_water_vapor_kg",
    "agent_efficiency",
]

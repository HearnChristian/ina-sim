from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Conditions:
    """Atmospheric / experiment conditions for a screen run."""

    temperature_c: float = -10.0
    relative_humidity_pct: float = 95.0
    pressure_hpa: float = 850.0
    # Cloud parcel / domain size for vapor inventory estimates
    cloud_volume_m3: float = 1_000_000.0
    # Seeding / particle loading (heuristic; not a full aerosol model)
    seeding_density_per_l: float = 100.0
    # Freezing mode for future multi-mode support
    mode: str = "immersion"  # immersion | deposition | contact

    def validate(self) -> None:
        if not (0.0 <= self.relative_humidity_pct <= 100.0):
            raise ValueError("relative_humidity_pct must be in [0, 100]")
        if self.pressure_hpa <= 0:
            raise ValueError("pressure_hpa must be positive")
        if self.cloud_volume_m3 <= 0:
            raise ValueError("cloud_volume_m3 must be positive")
        if self.seeding_density_per_l < 0:
            raise ValueError("seeding_density_per_l must be non-negative")

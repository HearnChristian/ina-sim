from __future__ import annotations

from dataclasses import asdict, dataclass

from ina_sim.physics.validate import (
    DENSITY_MAX_PER_L,
    DIAMETER_MAX_UM,
    DIAMETER_MIN_UM,
    P_MAX_HPA,
    P_MIN_HPA,
    T_MAX_C,
    T_MIN_C,
    VOLUME_MAX_M3,
    VOLUME_MIN_M3,
    require_finite,
)


@dataclass(frozen=True)
class Conditions:
    """Atmospheric / experiment conditions for a screen run."""

    temperature_c: float = -10.0
    relative_humidity_pct: float = 95.0
    pressure_hpa: float = 850.0
    cloud_volume_m3: float = 1_000_000.0
    seeding_density_per_l: float = 100.0
    mode: str = "immersion"  # immersion | deposition | contact
    particle_diameter_um: float = 1.0
    # ice = glaciogenic / INA ranking; warm_cloud = hygroscopic CCN ranking
    track: str = "ice"

    def validate(self) -> None:
        t = require_finite("temperature_c", self.temperature_c)
        if t <= -273.15:
            raise ValueError("temperature_c must be above absolute zero")
        if not (T_MIN_C <= t <= T_MAX_C):
            raise ValueError(
                f"temperature_c outside lab envelope [{T_MIN_C}, {T_MAX_C}] °C"
            )
        rh = require_finite("relative_humidity_pct", self.relative_humidity_pct)
        if not (0.0 <= rh <= 100.0):
            raise ValueError("relative_humidity_pct must be in [0, 100]")
        p = require_finite("pressure_hpa", self.pressure_hpa)
        if p <= 0:
            raise ValueError("pressure_hpa must be positive")
        if not (P_MIN_HPA <= p <= P_MAX_HPA):
            raise ValueError(
                f"pressure_hpa outside lab envelope [{P_MIN_HPA}, {P_MAX_HPA}]"
            )
        vol = require_finite("cloud_volume_m3", self.cloud_volume_m3)
        if not (VOLUME_MIN_M3 <= vol <= VOLUME_MAX_M3):
            raise ValueError("cloud_volume_m3 out of allowed range")
        dens = require_finite("seeding_density_per_l", self.seeding_density_per_l)
        if dens < 0 or dens > DENSITY_MAX_PER_L:
            raise ValueError("seeding_density_per_l out of allowed range")
        if self.mode not in {"immersion", "deposition", "contact"}:
            raise ValueError("mode must be immersion|deposition|contact")
        if self.track not in {"ice", "warm_cloud"}:
            raise ValueError("track must be ice|warm_cloud")
        d = require_finite("particle_diameter_um", self.particle_diameter_um)
        if not (DIAMETER_MIN_UM <= d <= DIAMETER_MAX_UM):
            raise ValueError(
                f"particle_diameter_um must be in [{DIAMETER_MIN_UM}, {DIAMETER_MAX_UM}] µm"
            )

    def as_dict(self) -> dict:
        return asdict(self)

    def clamped(self) -> Conditions:
        from ina_sim.physics.validate import (
            clamp,
            clamp_pressure_hpa,
            clamp_rh,
            clamp_temperature_c,
        )

        return Conditions(
            temperature_c=clamp_temperature_c(self.temperature_c),
            relative_humidity_pct=clamp_rh(self.relative_humidity_pct),
            pressure_hpa=clamp_pressure_hpa(self.pressure_hpa),
            cloud_volume_m3=clamp(
                require_finite("cloud_volume_m3", self.cloud_volume_m3),
                VOLUME_MIN_M3,
                VOLUME_MAX_M3,
            ),
            seeding_density_per_l=clamp(
                max(0.0, require_finite("seeding_density_per_l", self.seeding_density_per_l)),
                0.0,
                DENSITY_MAX_PER_L,
            ),
            mode=self.mode if self.mode in {"immersion", "deposition", "contact"} else "immersion",
            particle_diameter_um=clamp(
                require_finite("particle_diameter_um", self.particle_diameter_um),
                DIAMETER_MIN_UM,
                DIAMETER_MAX_UM,
            ),
            track=self.track if self.track in {"ice", "warm_cloud"} else "ice",
        )


def conditions_clamp_report(requested: Conditions, used: Conditions) -> dict:
    """Compare requested vs used; list fields that changed."""
    req = requested.as_dict()
    use = used.as_dict()
    changed = {k: {"requested": req[k], "used": use[k]} for k in req if req[k] != use[k]}
    return {
        "clamped": bool(changed),
        "fields": changed,
        "requested": req,
        "used": use,
    }

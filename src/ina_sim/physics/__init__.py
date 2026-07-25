"""Physics helpers package.

Import submodules directly (e.g. ``ina_sim.physics.atmosphere``) to avoid
eager circular imports with ``models.conditions``.
"""

# Keep package import light — do not re-export efficiency/atmosphere here.
__all__: list[str] = []

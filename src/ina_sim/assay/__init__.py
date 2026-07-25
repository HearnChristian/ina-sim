"""Import a droplet-freezing experiment and turn it into an ns(T) spectrum.

This is the path from a researcher's own cold-stage or microlitre-array run to
the same quantity the published parameterizations report, so their sample can be
compared against the literature on equal terms.

    ina-sim assay my_run.csv

See `ingest.py` for the accepted file shapes and `spectrum.py` for the
inversion, its uncertainty and the comparison against the registry.
"""

from ina_sim.assay.ingest import (
    AssayError,
    AssayMetadata,
    AssayReading,
    RawAssay,
    load_assay,
)
from ina_sim.assay.spectrum import (
    Comparison,
    Spectrum,
    SpectrumPoint,
    build_spectrum,
    compare_to_registry,
    wilson_interval,
)

__all__ = [
    "AssayError",
    "AssayMetadata",
    "AssayReading",
    "Comparison",
    "RawAssay",
    "Spectrum",
    "SpectrumPoint",
    "build_spectrum",
    "compare_to_registry",
    "load_assay",
    "wilson_interval",
]

"""Arbitrary-geometry ingestion + quality gating (Stage 18, ADR-033).

PLATFORM-NOT-HUB: this package imports stdlib + numpy + pydantic only. The STEP path
(:func:`aero.geometry.cad.load_step`) lazy-imports the CAD kernel behind ``aero[cad]``
inside the function — importing :mod:`aero.geometry` never touches it (enforced by the
``import-platform-only`` CI check).
"""

from aero.geometry._base import GeometryError, TriSurface
from aero.geometry.ingest import (
    IngestConfig,
    IngestedGeometry,
    QualityGateConfig,
    evaluate_gate,
    ingest,
)
from aero.geometry.quality import QualityReport, compute_quality
from aero.geometry.repair import RepairAction, RepairConfig, repair
from aero.geometry.stl import read_stl, write_stl
from aero.geometry.threemf import read_3mf

__all__ = [
    "GeometryError",
    "IngestConfig",
    "IngestedGeometry",
    "QualityGateConfig",
    "QualityReport",
    "RepairAction",
    "RepairConfig",
    "TriSurface",
    "compute_quality",
    "evaluate_gate",
    "ingest",
    "read_3mf",
    "read_stl",
    "repair",
    "write_stl",
]

"""External-geometry validation cases (Stage 18, ADR-033/034).

Cases that run on INGESTED external surfaces (not analytically generated ones)
through the full Stage-18 path: ingestion gate -> snappyHexMesh fallback ladder ->
CFD -> comparison against a published reference. Registry pattern mirrors
`aero.vv.forward_regime`.
"""

from aero.vv._base import BenchmarkCase
from aero.vv.external_geometry.turek_hron_cfd import TurekHronCFD2, TurekHronCFD3

EXTERNAL_GEOMETRY_CASES: dict[str, BenchmarkCase] = {
    TurekHronCFD2.name: TurekHronCFD2(),
    TurekHronCFD3.name: TurekHronCFD3(),
}

__all__ = ["EXTERNAL_GEOMETRY_CASES", "TurekHronCFD2", "TurekHronCFD3"]

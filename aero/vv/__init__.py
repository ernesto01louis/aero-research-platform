"""The aero V&V harness — canonical benchmark cases run against reference data.

A research platform without continuous V&V produces unverified numbers. This
package runs canonical verification cases (Stage 05: NASA TMR) through any
`SolverLike` solver, compares the result against published reference data with
tight tolerance bands, and records a `BenchmarkResult` keyed on the four-fold
provenance tuple.

`scipy` (pointwise interpolation) is an `aero[vv]` extra, imported lazily — so
`import aero.vv` stays within the PLATFORM-NOT-HUB dependency set.
"""

from __future__ import annotations

from aero.vv._base import (
    BenchmarkCase,
    BenchmarkError,
    BenchmarkResult,
    BenchmarkRunner,
    MetricResult,
    MetricSpec,
    ReferenceData,
    Series,
    SolverLike,
    compare,
    load_series_csv,
)
from aero.vv.mesh_sweep import (
    GridPoint,
    MeshSweep,
    SweepReport,
    grid_convergence_index,
)

__all__ = [
    "BenchmarkCase",
    "BenchmarkError",
    "BenchmarkResult",
    "BenchmarkRunner",
    "GridPoint",
    "MeshSweep",
    "MetricResult",
    "MetricSpec",
    "ReferenceData",
    "Series",
    "SolverLike",
    "SweepReport",
    "compare",
    "grid_convergence_index",
    "load_series_csv",
]

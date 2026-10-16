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
    ScalarObservation,
    Series,
    SolverLike,
    compare,
    load_scalar_csv,
    load_series_csv,
    scaled_count,
)
from aero.vv.dashboard import DashboardEntry, render_dashboard
from aero.vv.mesh_sweep import (
    GridPoint,
    MeshSweep,
    SweepReport,
    grid_convergence_index,
)
from aero.vv.stacks import CASE_STACK, DEFERRED_CASES, STACKS, SolverStack, registered_cases
from aero.vv.status import (
    VV_STATUSES,
    Disposition,
    StackName,
    StackVerdict,
    Verdict,
    VVStatus,
    stack_verdicts,
)

__all__ = [
    "CASE_STACK",
    "DEFERRED_CASES",
    "STACKS",
    "VV_STATUSES",
    "BenchmarkCase",
    "BenchmarkError",
    "BenchmarkResult",
    "BenchmarkRunner",
    "DashboardEntry",
    "Disposition",
    "GridPoint",
    "MeshSweep",
    "MetricResult",
    "MetricSpec",
    "ReferenceData",
    "ScalarObservation",
    "Series",
    "SolverLike",
    "SolverStack",
    "StackName",
    "StackVerdict",
    "SweepReport",
    "VVStatus",
    "Verdict",
    "compare",
    "grid_convergence_index",
    "load_scalar_csv",
    "load_series_csv",
    "registered_cases",
    "render_dashboard",
    "scaled_count",
    "stack_verdicts",
]

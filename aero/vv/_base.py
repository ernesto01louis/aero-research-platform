"""The solver-agnostic V&V benchmark harness.

A `BenchmarkCase` declares its solver input spec, its reference data, and the
metrics (with tolerance bands) to compare. `BenchmarkRunner` drives any case
through any solver that satisfies the `SolverLike` protocol — prepare, mesh,
run, evaluate, compare — and emits a `BenchmarkResult`, logging the four-fold
provenance tuple and per-metric errors to MLflow.

Nothing here imports a concrete solver: the OpenFOAM adapter satisfies
`SolverLike` structurally, and Stage 06's SU2 adapter will too. `scipy` (used
only for pointwise spline interpolation) is imported lazily inside `compare`
so `import aero.vv` stays within the PLATFORM-NOT-HUB dependency set.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aero.orchestration._base import Executor
from aero.provenance.four_fold import ProvenanceTuple

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

Comparison = Literal["relative", "normalized", "absolute"]
"""How a metric error is normalised. `relative`: per-point error / |reference|
(strictly-positive quantities, e.g. Cf). `normalized`: max|delta| / max|reference|
(sign-changing quantities, e.g. Cp). `absolute`: max|delta|."""


class BenchmarkError(RuntimeError):
    """A benchmark could not be evaluated (mesh failed, solve failed, no data)."""


# --- data models --------------------------------------------------------------
class Series(BaseModel):
    """A 1-D distribution — paired x and y samples, e.g. Cf along a wall."""

    model_config = _STRICT

    x: tuple[float, ...] = Field(..., description="Independent coordinate (sorted ascending).")
    y: tuple[float, ...] = Field(..., description="Dependent values, paired with `x`.")

    @model_validator(mode="after")
    def _same_length(self) -> Series:
        if len(self.x) != len(self.y):
            raise ValueError(f"x and y differ in length: {len(self.x)} vs {len(self.y)}")
        if len(self.x) < 2:
            raise ValueError("a Series needs at least two samples")
        return self


class MetricSpec(BaseModel):
    """One quantity to compare against reference, with its tolerance band."""

    model_config = _STRICT

    name: str = Field(..., min_length=1, description="Metric name, e.g. 'cd' or 'cf'.")
    kind: Literal["scalar", "pointwise"] = Field(..., description="Scalar value or x-distribution.")
    tolerance: float = Field(..., gt=0, description="Pass band, as a fraction (0.03 = 3%).")
    comparison: Comparison = Field(default="relative", description="Error normalisation.")


class MetricResult(BaseModel):
    """The compared outcome for one `MetricSpec`."""

    model_config = _STRICT

    name: str = Field(..., min_length=1)
    kind: Literal["scalar", "pointwise"]
    error: float = Field(..., ge=0, description="Normalised error against reference.")
    tolerance: float = Field(..., gt=0)
    passed: bool = Field(..., description="True iff error <= tolerance.")
    measured: float | None = Field(default=None, description="Measured scalar (scalar metrics).")
    reference: float | None = Field(default=None, description="Reference scalar (scalar metrics).")


class ReferenceData(BaseModel):
    """Published reference data a case is validated against."""

    model_config = _STRICT

    case_name: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1, description="Where the reference data came from.")
    series: dict[str, Series] = Field(default_factory=dict, description="Pointwise references.")
    scalars: dict[str, float] = Field(default_factory=dict, description="Scalar references.")


class BenchmarkResult(BaseModel):
    """The outcome of running one `BenchmarkCase` — the V&V record of the run."""

    model_config = _STRICT

    case_name: str = Field(..., min_length=1)
    status: Literal["pass", "fail", "regress"] = Field(..., description="Overall verdict.")
    metrics: tuple[MetricResult, ...] = Field(..., description="Per-metric compared outcomes.")
    provenance: ProvenanceTuple = Field(..., description="The four-fold provenance tuple.")
    solver_version: str = Field(..., min_length=1)
    validation_tag: str = Field(..., min_length=1, description="MLflow `validation_tag` value.")
    mlflow_run_id: str | None = Field(default=None)
    n_cells: int | None = Field(default=None, description="Mesh cell count, if reported.")

    def metric(self, name: str) -> MetricResult:
        """The `MetricResult` named `name` — raises if the case has no such metric."""
        for m in self.metrics:
            if m.name == name:
                return m
        raise KeyError(f"no metric {name!r} in benchmark result for {self.case_name}")

    def to_json(self) -> str:
        """Serialise to JSON — the artifact logged to MLflow and posted to PRs."""
        return self.model_dump_json(indent=2)


# --- protocols ----------------------------------------------------------------
@runtime_checkable
class SolverLike(Protocol):
    """The structural contract a solver must satisfy to drive a benchmark.

    The OpenFOAM adapter satisfies this; Stage 06's SU2 adapter will too. The
    harness never names a concrete solver class.
    """

    def prepare(self, case: Any) -> Any: ...
    def mesh(self, case_dir: Any, executor: Executor) -> Any: ...
    def run(self, case_dir: Any, executor: Executor) -> Any: ...
    def load(self, result: Any) -> Any: ...


@runtime_checkable
class BenchmarkCase(Protocol):
    """A canonical V&V case: a solver spec, reference data, and metrics."""

    name: str
    description: str

    def case_spec(self) -> Any:
        """The solver input spec (a `CaseSpec` or a `TMRCaseSpec`)."""
        ...

    def reference(self, repo_root: Path) -> ReferenceData:
        """Load the case's published reference data (DVC-tracked, under `data/`)."""
        ...

    def metrics(self) -> tuple[MetricSpec, ...]:
        """The metrics — with tolerance bands — this case is judged on."""
        ...

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        """Extract the measured value for each metric from a finished solve."""
        ...

    def refined(self, ratio: float) -> BenchmarkCase:
        """A copy of this case with mesh cell counts scaled by `1 / ratio`.

        `ratio >= 1` coarsens (a refinement ratio in the GCI sense); `ratio == 1`
        returns the base case. Used by `aero.vv.mesh_sweep.MeshSweep`.
        """
        ...


# --- comparison ---------------------------------------------------------------
def _scalar_error(measured: float, reference: float, comparison: Comparison) -> float:
    if comparison == "absolute":
        return abs(measured - reference)
    if reference == 0.0:
        raise BenchmarkError("relative comparison against a zero reference value")
    return abs(measured - reference) / abs(reference)


def _pointwise_error(measured: Series, reference: Series, comparison: Comparison) -> float:
    """Max error of `measured` interpolated onto the `reference` x-grid.

    The measured distribution is spline-interpolated onto the reference
    x-locations (restricted to the overlapping x-range); the per-point
    differences are then normalised per `comparison`.
    """
    from itertools import pairwise

    from scipy.interpolate import CubicSpline  # lazy — see module docstring

    mx = list(measured.x)
    my = list(measured.y)
    if any(b <= a for a, b in pairwise(mx)):
        raise BenchmarkError("measured Series x-coordinates are not strictly ascending")

    lo, hi = mx[0], mx[-1]
    pairs = [(rx, ry) for rx, ry in zip(reference.x, reference.y, strict=True) if lo <= rx <= hi]
    if len(pairs) < 2:
        raise BenchmarkError(
            f"measured x-range [{lo}, {hi}] overlaps fewer than 2 reference points"
        )
    spline = CubicSpline(mx, my)
    deltas = [abs(float(spline(rx)) - ry) for rx, ry in pairs]
    ref_vals = [ry for _, ry in pairs]

    if comparison == "absolute":
        return max(deltas)
    if comparison == "normalized":
        scale = max(abs(v) for v in ref_vals)
        if scale == 0.0:
            raise BenchmarkError("normalized comparison against an all-zero reference")
        return max(deltas) / scale
    # relative — per-point
    errs = []
    for d, ry in zip(deltas, ref_vals, strict=True):
        if ry == 0.0:
            raise BenchmarkError("relative comparison against a zero reference point")
        errs.append(d / abs(ry))
    return max(errs)


def compare(metric: MetricSpec, measured: float | Series, reference: ReferenceData) -> MetricResult:
    """Compare one measured quantity against reference, yielding a `MetricResult`."""
    if metric.kind == "scalar":
        if not isinstance(measured, int | float):
            raise BenchmarkError(f"metric {metric.name!r} is scalar but measured a Series")
        if metric.name not in reference.scalars:
            raise BenchmarkError(f"no scalar reference for metric {metric.name!r}")
        ref_val = reference.scalars[metric.name]
        error = _scalar_error(float(measured), ref_val, metric.comparison)
        return MetricResult(
            name=metric.name,
            kind="scalar",
            error=error,
            tolerance=metric.tolerance,
            passed=error <= metric.tolerance,
            measured=float(measured),
            reference=ref_val,
        )
    if not isinstance(measured, Series):
        raise BenchmarkError(f"metric {metric.name!r} is pointwise but measured a scalar")
    if metric.name not in reference.series:
        raise BenchmarkError(f"no pointwise reference for metric {metric.name!r}")
    error = _pointwise_error(measured, reference.series[metric.name], metric.comparison)
    return MetricResult(
        name=metric.name,
        kind="pointwise",
        error=error,
        tolerance=metric.tolerance,
        passed=error <= metric.tolerance,
    )


def load_series_csv(path: Path, *, x_col: str, y_col: str) -> Series:
    """Load a two-column `Series` from a header CSV, sorted ascending in x."""
    if not path.is_file():
        raise BenchmarkError(
            f"reference data not found: {path} — is the DVC remote pulled (`dvc pull`)?"
        )
    rows: list[tuple[float, float]] = []
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if x_col not in row or y_col not in row:
                raise BenchmarkError(f"{path} has no columns {x_col!r}/{y_col!r}")
            rows.append((float(row[x_col]), float(row[y_col])))
    rows.sort(key=lambda r: r[0])
    return Series(x=tuple(r[0] for r in rows), y=tuple(r[1] for r in rows))


class ScalarObservation(BaseModel):
    """One scalar measurement from a solve — the unit a mesh sweep collects."""

    model_config = _STRICT

    metric: str = Field(..., min_length=1)
    value: float = Field(...)
    n_cells: int | None = Field(default=None)
    mlflow_run_id: str | None = Field(default=None)


# --- runner -------------------------------------------------------------------
class BenchmarkRunner:
    """Drives a `BenchmarkCase` through a `SolverLike` and records the result."""

    def __init__(
        self,
        *,
        solver: SolverLike,
        executor: Executor,
        tracking_uri: str,
        experiment: str,
        db_dsn: str,
        solver_version: str,
        stage: str = "05",
    ) -> None:
        self.solver = solver
        self.executor = executor
        self.tracking_uri = tracking_uri
        self.experiment = experiment
        self.db_dsn = db_dsn
        self.solver_version = solver_version
        self.stage = stage

    def _drive(self, case: BenchmarkCase) -> tuple[dict[str, float | Series], Any, Any]:
        """prepare -> mesh -> solve -> evaluate; fail-loud on a mesh/solve failure."""
        spec = case.case_spec()
        case_dir = self.solver.prepare(spec)
        mesh = self.solver.mesh(case_dir, self.executor)
        if not getattr(mesh, "ok", False):
            raise BenchmarkError(f"{case.name}: blockMesh failed — case did not mesh")
        result = self.solver.run(case_dir, self.executor)
        if getattr(result, "returncode", 1) != 0:
            raise BenchmarkError(f"{case.name}: solver failed (rc={result.returncode})")
        measured = case.evaluate(self.solver, result)
        return measured, mesh, result

    def run(
        self,
        case: BenchmarkCase,
        *,
        provenance: ProvenanceTuple,
        repo_root: Path,
        log_mlflow: bool = True,
    ) -> BenchmarkResult:
        """Run `case` end-to-end and compare it against its reference data.

        prepare -> mesh -> solve -> evaluate -> compare. A mesh or solve
        failure raises `BenchmarkError` (fail-loud). When `log_mlflow` is set,
        the four-fold tuple and per-metric errors are logged to MLflow with a
        `validation_tag` tag.
        """
        measured, mesh, result = self._drive(case)
        reference = case.reference(repo_root)
        metric_results = tuple(compare(m, measured[m.name], reference) for m in case.metrics())
        status: Literal["pass", "fail"] = (
            "pass" if all(m.passed for m in metric_results) else "fail"
        )
        n_cells = getattr(mesh, "n_cells", None)

        mlflow_run_id: str | None = None
        if log_mlflow:
            mlflow_run_id = self._log(case, provenance, metric_results, result, n_cells)

        return BenchmarkResult(
            case_name=case.name,
            status=status,
            metrics=metric_results,
            provenance=provenance,
            solver_version=self.solver_version,
            validation_tag=case.name,
            mlflow_run_id=mlflow_run_id,
            n_cells=n_cells,
        )

    def measure_scalar(
        self,
        case: BenchmarkCase,
        metric: str,
        *,
        provenance: ProvenanceTuple,
        repo_root: Path,
        log_mlflow: bool = True,
    ) -> ScalarObservation:
        """Solve `case` and return one scalar measurement — no reference needed.

        This is the verification path the mesh sweep uses: a Grid Convergence
        Index compares a solution against itself at three resolutions, so it
        needs the measured scalar but not the (validation) reference data.
        """
        measured, mesh, result = self._drive(case)
        if metric not in measured:
            raise BenchmarkError(f"{case.name}: evaluate() produced no metric {metric!r}")
        value = measured[metric]
        if not isinstance(value, int | float):
            raise BenchmarkError(f"{case.name}: metric {metric!r} is not a scalar")
        n_cells = getattr(mesh, "n_cells", None)
        mlflow_run_id: str | None = None
        if log_mlflow:
            mlflow_run_id = self._log_scalar(case, provenance, metric, float(value), result)
        return ScalarObservation(
            metric=metric,
            value=float(value),
            n_cells=n_cells,
            mlflow_run_id=mlflow_run_id,
        )

    def _log(
        self,
        case: BenchmarkCase,
        provenance: ProvenanceTuple,
        metric_results: tuple[MetricResult, ...],
        result: Any,
        n_cells: int | None,
    ) -> str:
        """Log the run to MLflow — four-fold tags, per-metric errors, artifacts."""
        from aero.provenance.mlflow import log_artifact, log_metrics, start_provenance_run

        metrics: Mapping[str, float] = {f"{m.name}_error": m.error for m in metric_results}
        with start_provenance_run(
            tracking_uri=self.tracking_uri,
            experiment=self.experiment,
            provenance=provenance,
            case_name=case.name,
            db_dsn=self.db_dsn,
            stage=self.stage,
            extra_tags={"validation_tag": case.name, "solver_version": self.solver_version},
        ) as run:
            log_metrics(metrics)
            for m in metric_results:
                if m.measured is not None:
                    log_metrics({m.name: m.measured})
            pp = getattr(result, "post_processing_host_path", None)
            if pp is not None and Path(pp).exists():
                log_artifact(pp)
            return str(run.info.run_id)

    def _log_scalar(
        self,
        case: BenchmarkCase,
        provenance: ProvenanceTuple,
        metric: str,
        value: float,
        result: Any,
    ) -> str:
        """Log one mesh-sweep grid point to MLflow — the four-fold tuple + value."""
        from aero.provenance.mlflow import log_metrics, start_provenance_run

        with start_provenance_run(
            tracking_uri=self.tracking_uri,
            experiment=self.experiment,
            provenance=provenance,
            case_name=case.name,
            db_dsn=self.db_dsn,
            stage=self.stage,
            extra_tags={
                "validation_tag": f"{case.name}-sweep",
                "solver_version": self.solver_version,
            },
        ) as run:
            log_metrics({metric: value})
            return str(run.info.run_id)

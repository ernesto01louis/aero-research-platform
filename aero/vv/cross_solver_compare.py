"""Cross-solver V&V comparison — the headline Stage-06 V&V deliverable (ADR-006).

For each case, runs *both* the OpenFOAM and SU2 adapters through the same
`BenchmarkCase`, computes the per-metric discrepancy at converged states, and
flags any case where the two solvers disagree by more than the V&V tolerance.

Two solvers disagreeing more than their tolerance is a red flag — either a
mesh-quality issue (one solver more sensitive than the other) or a real model
discrepancy. The report is an MLflow artefact and is linked from the V&V
dashboard. We deliberately compare *output quantities at converged states*
(measured metrics), not fields — the two solvers' meshes differ (a polyMesh
C-grid vs. a `.su2` O-grid) and cross-mesh field comparison adds error a
case-level scalar/pointwise compare avoids.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aero.provenance.four_fold import ProvenanceTuple
from aero.vv._base import (
    BenchmarkCase,
    BenchmarkError,
    BenchmarkRunner,
    MetricSpec,
    Series,
    _pointwise_error,
    _scalar_error,
)

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)


class CrossSolverMetricResult(BaseModel):
    """One metric compared across two solvers — the per-metric verdict."""

    model_config = _STRICT

    name: str = Field(..., min_length=1)
    kind: Literal["scalar", "pointwise"]
    openfoam_value: float | None = Field(default=None, description="Scalar — only for scalar kind.")
    su2_value: float | None = Field(default=None, description="Scalar — only for scalar kind.")
    discrepancy: float = Field(
        ..., ge=0, description="Cross-solver discrepancy under `comparison`."
    )
    tolerance: float = Field(..., gt=0, description="Re-uses the case's V&V tolerance.")
    agrees: bool = Field(..., description="True iff `discrepancy <= tolerance`.")


class CrossSolverReport(BaseModel):
    """The cross-solver verdict for one `BenchmarkCase`."""

    model_config = _STRICT

    case_name: str = Field(..., min_length=1)
    openfoam_run_id: str | None = Field(default=None)
    su2_run_id: str | None = Field(default=None)
    metrics: tuple[CrossSolverMetricResult, ...]
    status: Literal["agree", "disagree", "failed"] = Field(
        ..., description="`agree` iff every metric agrees within tolerance."
    )

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    def to_markdown(self) -> str:
        """A short markdown table — the PR/dashboard rendering."""
        lines = [
            f"## Cross-solver verdict — `{self.case_name}` ({self.status})",
            "",
            "| Metric | Kind | OpenFOAM | SU2 | Discrepancy | Tolerance | Agree |",
            "|---|---|---|---|---:|---:|:---:|",
        ]
        for m in self.metrics:
            of = "—" if m.openfoam_value is None else f"{m.openfoam_value:.6g}"
            su = "—" if m.su2_value is None else f"{m.su2_value:.6g}"
            tick = "✅" if m.agrees else "❌"
            lines.append(
                f"| {m.name} | {m.kind} | {of} | {su} | {m.discrepancy:.4%} | "
                f"{m.tolerance:.1%} | {tick} |"
            )
        return "\n".join(lines) + "\n"


def _drive_solver(
    runner: BenchmarkRunner,
    case: BenchmarkCase,
    *,
    provenance: ProvenanceTuple,
    repo_root: Path,
) -> tuple[dict[str, float | Series], str | None]:
    """Run a case through one solver and return the measured metric dict.

    Uses `BenchmarkRunner.run` so the four-fold provenance tuple and per-metric
    errors are logged to MLflow exactly as for a normal V&V run. We surface the
    MLflow run id for the report.
    """
    result = runner.run(case, provenance=provenance, repo_root=repo_root)
    # Re-evaluate to recover the measured metric values — `BenchmarkResult`
    # carries the *errors against reference*, not the raw measured values for
    # pointwise metrics. The harness has the case re-evaluate cheaply once.
    measured, _, _ = runner._drive(case)
    return measured, result.mlflow_run_id


def _compare_one(
    metric: MetricSpec,
    openfoam: float | Series,
    su2: float | Series,
) -> CrossSolverMetricResult:
    """Per-metric cross-solver comparison under the metric's V&V comparison mode."""
    if metric.kind == "scalar":
        if not (isinstance(openfoam, int | float) and isinstance(su2, int | float)):
            raise BenchmarkError(f"metric {metric.name!r} scalar but a measurement was a Series")
        # Treat su2 as 'measured', openfoam as 'reference' for the
        # `comparison`-normalised error (symmetric for `relative` when both
        # positive; `normalized`/`absolute` are symmetric by construction).
        discrepancy = _scalar_error(float(su2), float(openfoam), metric.comparison)
        return CrossSolverMetricResult(
            name=metric.name,
            kind="scalar",
            openfoam_value=float(openfoam),
            su2_value=float(su2),
            discrepancy=discrepancy,
            tolerance=metric.tolerance,
            agrees=discrepancy <= metric.tolerance,
        )
    if not (isinstance(openfoam, Series) and isinstance(su2, Series)):
        raise BenchmarkError(f"metric {metric.name!r} pointwise but a measurement was a scalar")
    discrepancy = _pointwise_error(su2, openfoam, metric.comparison)
    return CrossSolverMetricResult(
        name=metric.name,
        kind="pointwise",
        openfoam_value=None,
        su2_value=None,
        discrepancy=discrepancy,
        tolerance=metric.tolerance,
        agrees=discrepancy <= metric.tolerance,
    )


def compare_solvers(
    case: BenchmarkCase,
    *,
    openfoam_runner: BenchmarkRunner,
    su2_runner: BenchmarkRunner,
    openfoam_provenance: ProvenanceTuple,
    su2_provenance: ProvenanceTuple,
    repo_root: Path,
) -> CrossSolverReport:
    """Run `case` through both solvers and emit a `CrossSolverReport`.

    Per-metric discrepancy uses the case's own `MetricSpec.comparison` so a
    Cd disagreement reads on the same scale as the V&V tolerance the case
    publishes. A case where SU2 and OpenFOAM disagree by more than the V&V
    tolerance is a red flag — see the module docstring.
    """
    try:
        of_measured, of_run_id = _drive_solver(
            openfoam_runner, case, provenance=openfoam_provenance, repo_root=repo_root
        )
        su_measured, su_run_id = _drive_solver(
            su2_runner, case, provenance=su2_provenance, repo_root=repo_root
        )
    except BenchmarkError:
        # Surface the failure as an explicit `failed` status, not a fake agree.
        return CrossSolverReport(
            case_name=case.name,
            metrics=(),
            status="failed",
            openfoam_run_id=None,
            su2_run_id=None,
        )

    per_metric = tuple(
        _compare_one(m, of_measured[m.name], su_measured[m.name]) for m in case.metrics()
    )
    status: Literal["agree", "disagree"] = (
        "agree" if all(m.agrees for m in per_metric) else "disagree"
    )
    return CrossSolverReport(
        case_name=case.name,
        metrics=per_metric,
        status=status,
        openfoam_run_id=of_run_id,
        su2_run_id=su_run_id,
    )


def write_report(report: CrossSolverReport, out_dir: Path) -> tuple[Path, Path]:
    """Write the JSON and markdown renderings under `out_dir`. Returns `(json, md)`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{report.case_name}.json"
    md_path = out_dir / f"{report.case_name}.md"
    json_path.write_text(json.dumps(json.loads(report.to_json()), indent=2), encoding="utf-8")
    md_path.write_text(report.to_markdown(), encoding="utf-8")
    return json_path, md_path


__all__ = [
    "CrossSolverMetricResult",
    "CrossSolverReport",
    "compare_solvers",
    "write_report",
]

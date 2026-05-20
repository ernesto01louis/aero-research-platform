"""Stage 06 — cross-solver comparison report shape (no cluster, no solvers).

`compare_solvers` runs both adapters on a case; this unit test exercises the
per-metric comparison and the markdown/JSON rendering through `_compare_one`
directly (no `BenchmarkRunner` needed), so the contract is locked without a
real CFD run.
"""

from __future__ import annotations

import json

import pytest
from aero.vv._base import MetricSpec, Series
from aero.vv.cross_solver_compare import (
    CrossSolverMetricResult,
    CrossSolverReport,
    _compare_one,
)

pytestmark = pytest.mark.stage_06


def test_scalar_agreement_within_tolerance() -> None:
    metric = MetricSpec(name="cd", kind="scalar", tolerance=0.03, comparison="relative")
    r = _compare_one(metric, openfoam=0.00812, su2=0.00820)
    assert r.kind == "scalar"
    assert r.openfoam_value == pytest.approx(0.00812)
    assert r.su2_value == pytest.approx(0.00820)
    assert r.discrepancy == pytest.approx(abs(0.00820 - 0.00812) / 0.00812)
    assert r.agrees  # ~1% < 3%


def test_scalar_disagreement_outside_tolerance() -> None:
    metric = MetricSpec(name="cd", kind="scalar", tolerance=0.03, comparison="relative")
    r = _compare_one(metric, openfoam=0.00812, su2=0.00950)
    assert not r.agrees
    assert r.discrepancy > metric.tolerance


def test_pointwise_agreement_uses_spline_interpolation() -> None:
    metric = MetricSpec(name="cp", kind="pointwise", tolerance=0.05, comparison="normalized")
    of = Series(x=(0.0, 0.5, 1.0), y=(1.0, 0.0, -1.0))
    su = Series(x=(0.0, 0.5, 1.0), y=(1.01, 0.02, -0.99))
    r = _compare_one(metric, openfoam=of, su2=su)
    assert r.kind == "pointwise"
    assert r.openfoam_value is None and r.su2_value is None
    assert r.discrepancy <= metric.tolerance


def test_report_to_markdown_renders_a_table() -> None:
    rows = (
        CrossSolverMetricResult(
            name="cd",
            kind="scalar",
            openfoam_value=0.00812,
            su2_value=0.00820,
            discrepancy=0.01,
            tolerance=0.03,
            agrees=True,
        ),
    )
    report = CrossSolverReport(
        case_name="naca0012_verification",
        metrics=rows,
        status="agree",
        openfoam_run_id="of-1",
        su2_run_id="su-1",
    )
    md = report.to_markdown()
    assert "naca0012_verification" in md
    assert "OpenFOAM" in md and "SU2" in md
    assert "✅" in md  # passing tick
    # JSON round-trip stays a strict pydantic model.
    parsed = json.loads(report.to_json())
    assert parsed["status"] == "agree"
    assert parsed["metrics"][0]["name"] == "cd"

"""Stage 06 V&V test — TMR 2D bump-in-channel through SU2 (cluster-bound).

The bump case has two checks (Cp/Cf validation + a GCI mesh sweep on the
suction-peak Cp). Both run through SU2 unchanged. `xfail(strict=False)` until
the SU2 path is cluster-validated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aero.vv import BenchmarkError, MeshSweep
from aero.vv.tmr import Bump2D

pytestmark = [pytest.mark.slow, pytest.mark.vv, pytest.mark.stage_06]

_XFAIL_REASON = (
    "SU2 v8 TMR 2D bump not yet cluster-validated; Stage-06 deliverable is "
    "the cross-solver comparison, see ADR-006."
)


@pytest.mark.xfail(reason=_XFAIL_REASON, strict=False)
def test_bump_2d_cp_cf_within_tolerance_su2(
    vv_cluster_ready_su2: bool, vv_runner_su2: Any, repo_root: Path
) -> None:
    if not vv_cluster_ready_su2:
        pytest.skip("SU2 V&V cluster not ready")
    runner, provenance_of = vv_runner_su2
    case = Bump2D()
    try:
        result = runner.run(case, provenance=provenance_of(case.case_spec()), repo_root=repo_root)
    except BenchmarkError as exc:
        pytest.skip(f"bump_2d reference data not present: {exc}")
    assert result.status == "pass", (
        "SU2 bump 2D Cp/Cf one or more metrics exceeded their tolerance: "
        + ", ".join(f"{m.name} {m.error:.2%}" for m in result.metrics if not m.passed)
    )


@pytest.mark.mesh_sweep
@pytest.mark.xfail(reason=_XFAIL_REASON, strict=False)
def test_bump_2d_grid_converged_cp_min_su2(
    vv_cluster_ready_su2: bool, vv_runner_su2: Any, repo_root: Path
) -> None:
    if not vv_cluster_ready_su2:
        pytest.skip("SU2 V&V cluster not ready")
    runner, provenance_of = vv_runner_su2
    case = Bump2D()
    report = MeshSweep(case, metric="cp_min").run(
        runner, provenance=provenance_of(case.case_spec()), repo_root=repo_root
    )
    assert report.monotonic, "SU2 bump cp_min sweep is non-monotone — grid convergence not shown"

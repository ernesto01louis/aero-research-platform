"""Stage 06 V&V test — TMR turbulent flat plate Cf through SU2 (cluster-bound).

Same `BenchmarkCase` as Stage 05 (`FlatPlateTE`), same 5% pointwise Cf
tolerance — only the solver changes. `xfail(strict=False)` until cluster
validation lands.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aero.vv.tmr import FlatPlateTE

pytestmark = [pytest.mark.slow, pytest.mark.vv, pytest.mark.stage_06]

_XFAIL_REASON = (
    "SU2 v8 TMR flat plate not yet cluster-validated; Stage-06 deliverable is "
    "the cross-solver comparison, see ADR-006. "
    "[resolution-milestone: cluster-validation]"
)


@pytest.mark.xfail(reason=_XFAIL_REASON, strict=False)
def test_flat_plate_cf_within_tolerance_su2(
    vv_cluster_ready_su2: bool, vv_runner_su2: Any, repo_root: Path
) -> None:
    if not vv_cluster_ready_su2:
        pytest.skip("SU2 V&V cluster not ready")
    runner, provenance_of = vv_runner_su2
    case = FlatPlateTE()
    result = runner.run(case, provenance=provenance_of(case.case_spec()), repo_root=repo_root)
    cf = result.metric("cf")
    assert result.status == "pass", (
        f"SU2 flat-plate Cf error {cf.error:.2%} exceeds {cf.tolerance:.0%}"
    )

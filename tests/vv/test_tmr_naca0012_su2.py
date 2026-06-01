"""Stage 06 V&V test — NACA 0012 drag verification through SU2 (cluster-bound).

Mirrors `test_tmr_naca0012.py` but drives the case through the SU2 v8 adapter.
The `NACA0012Verification` `BenchmarkCase` is solver-agnostic; only the runner
changes. Same tolerance, no relaxation (Stage-06 guardrail 2 / Stage-05 §0).

`xfail(strict=False)` because Stage 06 has not yet cluster-validated SU2
against the TMR cases — the headline Stage-06 V&V deliverable is the
cross-solver comparison report, not a green SU2 single-grid pass. A genuine
pass un-xfails cleanly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aero.vv.tmr import NACA0012Verification

pytestmark = [pytest.mark.slow, pytest.mark.vv, pytest.mark.stage_06]

_XFAIL_REASON = (
    "SU2 v8 NACA 0012 not yet cluster-validated against the TMR reference; "
    "Stage-06 deliverable is the cross-solver comparison, see ADR-006. "
    "[resolution-milestone: cluster-validation]"
)


@pytest.mark.xfail(reason=_XFAIL_REASON, strict=False)
def test_naca0012_cd_within_tolerance_su2(
    vv_cluster_ready_su2: bool, vv_runner_su2: Any, repo_root: Path
) -> None:
    """SU2's single-grid Cd lands within 3% of the TMR reference."""
    if not vv_cluster_ready_su2:
        pytest.skip("SU2 V&V cluster not ready")
    runner, provenance_of = vv_runner_su2
    case = NACA0012Verification()
    result = runner.run(case, provenance=provenance_of(case.case_spec()), repo_root=repo_root)
    cd = result.metric("cd")
    assert result.status == "pass", (
        f"SU2 NACA 0012 Cd error {cd.error:.2%} exceeds {cd.tolerance:.0%}"
    )

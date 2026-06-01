"""Stage 06 V&V test — transonic NACA 0012 Cd through SU2 (cluster-bound, slow).

Drives the `NACA0012Transonic` `BenchmarkCase` (M=0.7, AoA=1.49 deg, Re=9e6)
through SU2 and compares the converged Cd against the AGARD-AR-138 /
Schmitt-Charpin reference at the 5% tolerance set in ADR-006. `xfail(strict=
False)` until the first cluster run lands (Stage-06 partial; tightening to a
GCI mesh sweep is Stage 12).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aero.vv.transonic import NACA0012Transonic

pytestmark = [pytest.mark.slow, pytest.mark.vv, pytest.mark.stage_06]

_XFAIL_REASON = (
    "Transonic NACA 0012 SU2 path not yet cluster-validated; the O-grid mesh "
    "the adapter generates is not yet the grid-converged Cd grid (ADR-006). "
    "[resolution-milestone: cluster-validation]"
)


@pytest.mark.xfail(reason=_XFAIL_REASON, strict=False)
def test_transonic_naca0012_cd_within_tolerance(
    vv_cluster_ready_su2: bool, vv_runner_su2: Any, repo_root: Path
) -> None:
    if not vv_cluster_ready_su2:
        pytest.skip("SU2 V&V cluster not ready")
    runner, provenance_of = vv_runner_su2
    case = NACA0012Transonic()
    result = runner.run(case, provenance=provenance_of(case.case_spec()), repo_root=repo_root)
    cd = result.metric("cd")
    assert result.status == "pass", (
        f"SU2 transonic Cd error {cd.error:.2%} exceeds {cd.tolerance:.0%}"
    )

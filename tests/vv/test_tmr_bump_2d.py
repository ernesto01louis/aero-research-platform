"""Stage 05 V&V test — NASA TMR 2D bump-in-channel (cluster-bound, slow).

The bump's *verification* is a GCI mesh sweep (no reference data needed); its
*validation* (Cp/Cf vs. TMR data) is skipped until the TMR data files are
mirrored — see data/references/tmr/bump_2d/reference.md.

KNOWN FAILURE (Stage 05, xfail) — the bump now *solves* (the Stage-05 fix pass
switched its pressure solver to PCG/DIC, which the long-channel high-aspect-
ratio cells need — GAMG stalled), but it does not yet converge tightly
(p residual ~3e-4 at 3000 iterations) and its Cp/Cf are well off the TMR data
(~24% / ~64%). The GCI machinery is unit-tested (`test_gci.py`) and correct;
the bump *case* needs convergence and domain tuning. Stage-05 open item.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aero.vv import MeshSweep
from aero.vv.tmr import Bump2D

pytestmark = [pytest.mark.slow, pytest.mark.vv, pytest.mark.stage_05]


@pytest.mark.mesh_sweep
@pytest.mark.xfail(
    reason="bump solves (PCG) but does not converge tightly enough for a "
    "reliable GCI; needs convergence/domain tuning — Stage-05 open item. "
    "[resolution-milestone: stage-10 bump-convergence]",
    strict=False,
)
def test_bump_gci_mesh_sweep(vv_cluster_ready: bool, vv_runner: Any, repo_root: Path) -> None:
    """A 3-grid GCI study converges and reports an order of accuracy."""
    if not vv_cluster_ready:
        pytest.skip("V&V cluster not ready")
    runner, provenance_of = vv_runner
    case = Bump2D()
    sweep = MeshSweep(case, metric=case.sweep_metric)
    report = sweep.run(runner, provenance=provenance_of(case.case_spec()), repo_root=repo_root)
    assert report.monotonic, "bump GCI sweep is non-monotone — convergence not established"
    assert report.observed_order_p > 0.0
    assert report.gci_fine_pct >= 0.0

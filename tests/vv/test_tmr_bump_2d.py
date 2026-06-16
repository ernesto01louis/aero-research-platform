"""Stage 05 V&V test — NASA TMR 2D bump-in-channel (cluster-bound, slow).

The bump's *verification* is a GCI mesh sweep (no reference data needed); its
*validation* (Cp/Cf vs. TMR data) is skipped until the TMR data files are
mirrored — see data/references/tmr/bump_2d/reference.md.

KNOWN FAILURE (Stage 05 origin, xfail) — the bump *solves* (PCG/DIC; GAMG
stalled on the long-channel high-aspect-ratio cells) but does not reach tight
iterative convergence, so the suction-peak `cp_min` the GCI sweep tracks is
not cleanly grid-converged.

STAGE-10 CONCERN (confirmed, not resolved) — a single-grid diagnostic at
end_time=8000 confirmed the p initial-residual **plateaus at ~2-5e-4 from
~iter 2000 through 4000+** and never reaches the 1e-6 residualControl target;
it is a genuine convergence stall (likely low-level unsteadiness / stiff
turbulence coupling in the long channel), NOT an iteration-count shortfall —
more iterations do not break it. The GCI machinery is unit-tested (`test_gci.py`)
and correct; the bump *case* needs a dedicated convergence pass (relaxation /
turbulence-numerics / domain tuning) or a transient time-averaged treatment
(the Stage-11 unsteady path). The tolerance is NOT relaxed; the test stays
xfail. See ADR-017 and the Stage-10 handoff. [resolution-milestone: deferred]
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
    reason="bump solves (PCG) but the p initial-residual plateaus at ~3e-4 "
    "(confirmed Stage-10 to ~iter 4000+, not iteration-limited), so cp_min is "
    "not grid-converged for a reliable GCI; needs a dedicated convergence pass "
    "or a transient-mean treatment (Stage 11). Tolerance NOT relaxed; see "
    "ADR-017. [resolution-milestone: deferred]",
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

"""Stage 05 V&V test — NASA TMR 2D bump-in-channel (cluster-bound, slow).

The bump's *verification* is a GCI mesh sweep (no reference data needed); its
*validation* (Cp/Cf vs. TMR data) is skipped until the TMR data files are
mirrored — see data/references/tmr/bump_2d/reference.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aero.vv import MeshSweep
from aero.vv.tmr import Bump2D

pytestmark = [pytest.mark.slow, pytest.mark.vv, pytest.mark.stage_05]


@pytest.mark.mesh_sweep
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

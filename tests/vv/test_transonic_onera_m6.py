"""Stage 06 V&V test — ONERA M6 Cp through SU2 (cluster-bound, slow).

The 3D wing case cannot pass until two pieces land (Stage-06 partial, ADR-006).
Since Stage 22 it FAILS loudly instead of skipping (ADR-051); it is `su2`-marked,
so only the vv-transonic dispatch runs it:

* the DVC-tracked Cp reference data (`data/references/transonic/onera_m6/
  cp_station_0.44.csv`) — Schmitt-Charpin / ONERA TR-1; and
* the host-side wing-slice extraction for `wall_distribution` on a 3D wing
  (slice on y at η=0.44).

The Cp reference CSVs are committed in-tree; the mesh is DVC-tracked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aero.vv.transonic import OneraM6

# `su2`: the frozen-optional SU2 stack (ADR-013, ADR-051 D2). The active-stack jobs deselect
# it; only the vv-transonic dispatch measures it (Stage 22).
pytestmark = [pytest.mark.slow, pytest.mark.vv, pytest.mark.stage_06, pytest.mark.su2]


def test_onera_m6_cp_at_eta_044(
    vv_cluster_ready_su2: bool, vv_runner_su2: Any, repo_root: Path
) -> None:
    if not vv_cluster_ready_su2:
        pytest.skip("SU2 V&V cluster not ready")
    runner, provenance_of = vv_runner_su2
    case = OneraM6()
    # No try/except (Stage 22). This used to turn every error into a skip, so the nightly job
    # was green while SU2 died at startup ("solver failed (rc=1)") and the mesh question was
    # misread. The mesh is fetched by a targeted, fail-loud `dvc pull` in vv-transonic; a
    # missing mesh, a solver failure, or the unimplemented eta=0.44 slice
    # (`OneraM6.evaluate`) all FAIL here, which is the truth about this case today.
    result = runner.run(case, provenance=provenance_of(case), repo_root=repo_root)
    cp = result.metric("cp")
    assert result.status == "pass", (
        f"SU2 ONERA M6 Cp error {cp.error:.2%} exceeds {cp.tolerance:.0%}"
    )

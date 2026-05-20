"""Stage 06 V&V test — ONERA M6 Cp through SU2 (cluster-bound, slow).

The 3D wing case is harness-skipped until two pieces land (Stage-06 partial,
ADR-006):

* the DVC-tracked Cp reference data (`data/references/transonic/onera_m6/
  cp_station_0.44.csv`) — Schmitt-Charpin / ONERA TR-1; and
* the host-side wing-slice extraction for `wall_distribution` on a 3D wing
  (slice on y at η=0.44).

The skip is explicit and surfaces in CI as the data/feature gap, not a fake
green.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aero.vv import BenchmarkError
from aero.vv.transonic import OneraM6

pytestmark = [pytest.mark.slow, pytest.mark.vv, pytest.mark.stage_06]


def test_onera_m6_cp_at_eta_044(
    vv_cluster_ready_su2: bool, vv_runner_su2: Any, repo_root: Path
) -> None:
    if not vv_cluster_ready_su2:
        pytest.skip("SU2 V&V cluster not ready")
    runner, provenance_of = vv_runner_su2
    case = OneraM6()
    try:
        result = runner.run(case, provenance=provenance_of(case.case_spec()), repo_root=repo_root)
    except (BenchmarkError, FileNotFoundError) as exc:
        # FileNotFoundError covers the DVC-tracked mesh missing from a fresh
        # checkout (no `dvc pull` configured); BenchmarkError covers the Cp
        # reference data missing. Both surface as "skip" rather than fail.
        pytest.skip(f"ONERA M6 not yet runnable: {exc}")
    cp = result.metric("cp")
    assert result.status == "pass", (
        f"SU2 ONERA M6 Cp error {cp.error:.2%} exceeds {cp.tolerance:.0%}"
    )

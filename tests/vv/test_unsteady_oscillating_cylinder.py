"""Stage 11 V&V test — oscillating-cylinder lock-in (cluster-bound, slow).

A forced transversely-oscillating cylinder (Re=100, A/D=0.5, F=1.1) must reach a periodic
steady state and its wake must lock to the forcing frequency: the FFT-recovered response
Strouhal within 3% of the forcing St = 0.1815. The Stage-11 primary GO. Cluster-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aero.vv.unsteady import OscillatingCylinderLockin

pytestmark = [pytest.mark.slow, pytest.mark.vv, pytest.mark.moving, pytest.mark.stage_11]


def test_oscillating_cylinder_locks_in(
    vv_cluster_ready: bool, vv_runner: Any, repo_root: Path
) -> None:
    """The forced cylinder wake locks to the forcing frequency (St within 3%)."""
    if not vv_cluster_ready:
        pytest.skip("V&V cluster not ready (SSH / SIF / extras / AERO_PROVENANCE_DSN)")
    runner, provenance_of = vv_runner
    case = OscillatingCylinderLockin()
    result = runner.run(case, provenance=provenance_of(case.case_spec()), repo_root=repo_root)
    st = result.metric("strouhal")
    assert result.status == "pass", (
        f"cylinder lock-in St error {st.error:.2%} exceeds {st.tolerance:.0%} "
        "(not locked to the forcing?)"
    )

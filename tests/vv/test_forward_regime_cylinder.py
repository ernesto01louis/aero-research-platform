"""Stage 10 V&V test — transient cylinder Strouhal at Re=100 (cluster-bound, slow).

Forward-regime vortex shedding: a transient pimpleFoam solve must shed and the
lift-FFT must recover St within 5% of the Roshko/Williamson value 0.165. This
PASSES (validated on aero-dev: St error 4.0%) — a real assertion, not an xfail.
The platform's first transient OpenFOAM V&V case.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aero.vv.forward_regime import CylinderStrouhal

pytestmark = [pytest.mark.slow, pytest.mark.vv, pytest.mark.stage_10]


def test_cylinder_strouhal_within_tolerance(
    vv_cluster_ready: bool, vv_runner: Any, repo_root: Path
) -> None:
    """A transient cylinder solve sheds with St within 5% of 0.165."""
    if not vv_cluster_ready:
        pytest.skip("V&V cluster not ready (SSH / SIF / extras / AERO_PROVENANCE_DSN)")
    runner, provenance_of = vv_runner
    case = CylinderStrouhal()
    result = runner.run(case, provenance=provenance_of(case.case_spec()), repo_root=repo_root)
    st = result.metric("strouhal")
    assert result.status == "pass", f"cylinder St error {st.error:.2%} exceeds {st.tolerance:.0%}"

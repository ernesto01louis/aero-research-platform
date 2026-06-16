"""Stage 10 V&V test — laminar NACA 0012 at Re=1000 (cluster-bound, slow).

Forward-regime low-Re airfoil: a steady laminar solve must return Cl ~= 0
(symmetry, absolute 0.01) and Cd within 10% of the Kurtuluş (2015) value 0.12.
This PASSES (validated on aero-dev: Cl error 0.23%, Cd error 0.16%) — a real
assertion, not an xfail.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aero.vv.forward_regime import LaminarAirfoil

pytestmark = [pytest.mark.slow, pytest.mark.vv, pytest.mark.stage_10]


def test_laminar_airfoil_within_tolerance(
    vv_cluster_ready: bool, vv_runner: Any, repo_root: Path
) -> None:
    """A laminar NACA 0012 (Re=1000, AoA=0) solve passes the Cl-symmetry + low-Re-Cd metrics."""
    if not vv_cluster_ready:
        pytest.skip("V&V cluster not ready (SSH / SIF / extras / AERO_PROVENANCE_DSN)")
    runner, provenance_of = vv_runner
    case = LaminarAirfoil()
    result = runner.run(case, provenance=provenance_of(case.case_spec()), repo_root=repo_root)
    assert result.status == "pass", (
        f"laminar airfoil: cl error {result.metric('cl').error:.2%}, "
        f"cd error {result.metric('cd').error:.2%}"
    )

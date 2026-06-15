"""Stage 10 V&V test — Blasius laminar flat plate (cluster-bound, slow).

The forward-regime laminar skin-friction check: a steady laminar solve must
match the exact Blasius law (Cf = 0.664/sqrt(Re_x)) within 5% pointwise over the
developed plate. Unlike the turbulent TMR cases this PASSES (the laminar
discretisation reproduces the known boundary layer) — validated on aero-dev at
Cf error ~2.15%, MLflow run logged. This is a real assertion, not an xfail.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aero.vv.forward_regime import BlasiusFlatPlate

pytestmark = [pytest.mark.slow, pytest.mark.vv, pytest.mark.stage_10]


def test_blasius_flat_plate_cf_within_tolerance(
    vv_cluster_ready: bool, vv_runner: Any, repo_root: Path
) -> None:
    """A laminar flat-plate solve lands within 5% of the Blasius Cf law."""
    if not vv_cluster_ready:
        pytest.skip("V&V cluster not ready (SSH / SIF / extras / AERO_PROVENANCE_DSN)")
    runner, provenance_of = vv_runner
    case = BlasiusFlatPlate()
    result = runner.run(case, provenance=provenance_of(case.case_spec()), repo_root=repo_root)
    cf = result.metric("cf")
    assert result.status == "pass", f"Blasius Cf error {cf.error:.2%} exceeds {cf.tolerance:.0%}"

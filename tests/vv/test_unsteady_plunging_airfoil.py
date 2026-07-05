"""Stage 11 V&V test — plunging-airfoil thrust vs Heathcote-Gursul (cluster-bound, slow).

A rigid plunging NACA-0012 (Re=1e4, h0/c=0.175, St=0.4) must reach a periodic steady state
and its time-averaged thrust coefficient must match the Heathcote & Gursul (2007) rigid-foil
value within the 15% honest band. Laminar 2-D. Cluster-only, multi-hour.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aero.vv.unsteady import PlungingAirfoilHG2007

pytestmark = [pytest.mark.slow, pytest.mark.vv, pytest.mark.moving, pytest.mark.stage_11]


def test_plunging_airfoil_thrust_within_band(
    vv_cluster_ready: bool, vv_runner: Any, repo_root: Path
) -> None:
    """The plunging foil's mean thrust matches Heathcote-Gursul within 15%."""
    if not vv_cluster_ready:
        pytest.skip("V&V cluster not ready (SSH / SIF / extras / AERO_PROVENANCE_DSN)")
    runner, provenance_of = vv_runner
    case = PlungingAirfoilHG2007()
    result = runner.run(case, provenance=provenance_of(case.case_spec()), repo_root=repo_root)
    ct = result.metric("thrust_coefficient")
    assert result.status == "pass", (
        f"plunging-foil C_T error {ct.error:.2%} exceeds {ct.tolerance:.0%} "
        "(investigate; fall back to the trend check, do not relax the tolerance)"
    )

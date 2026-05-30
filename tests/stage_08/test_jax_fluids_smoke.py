"""Stage 08 — JAX-Fluids 1D Sod shock-tube smoke test (cluster + SIF gated).

Skips when the JAX-Fluids SIF isn't present (mirror of Stage-07's PyFR
cluster-smoke pattern). When green, asserts the shock position falls
within ±2% of the analytic Riemann-problem solution.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.jax_fluids import JaxFluidsShockTubeSpec, JaxFluidsSolver

pytestmark = [pytest.mark.stage_08, pytest.mark.slow]

# Analytic shock-front position at t = 0.2 for Sod's 1-D Riemann problem.
# Computed offline (HLLC reference); ±2% tolerance is the canonical
# JAX-Fluids tutorial bar.
_ANALYTIC_SHOCK_POSITION = 0.785
_TOLERANCE = 0.02 * _ANALYTIC_SHOCK_POSITION


def test_jax_fluids_shock_tube_smoke(
    jax_fluids_sif_present: bool,
    jax_fluids_extra_installed: bool,
    tmp_path: Path,
) -> None:
    if not jax_fluids_sif_present:
        pytest.skip("JAX-Fluids SIF not published on aero-build (operator follow-up)")
    if not jax_fluids_extra_installed:
        pytest.skip("aero[jax-fluids,provenance] host-side extras not installed")

    from aero.orchestration.ssh import LocalSSHExecutor

    spec = JaxFluidsShockTubeSpec(name="sod-256-smoke", n_cells=256, t_end=0.2)
    solver = JaxFluidsSolver(host_nfs_root=tmp_path, remote_nfs_root=tmp_path)
    executor = LocalSSHExecutor(host="aero-build", ssh_user="root", repo_root=tmp_path)

    case_dir = solver.prepare(spec)
    mesh = solver.mesh(case_dir, executor)
    assert mesh.ok and mesh.n_elements == 256
    result = solver.run(case_dir, executor)
    assert result.returncode == 0, f"solve failed:\n{result.solver_log}"
    solve = solver.load(result)
    shock = solve.scalars["shock_position"]
    assert abs(shock - _ANALYTIC_SHOCK_POSITION) < _TOLERANCE, (
        f"shock at {shock:.3f}, expected {_ANALYTIC_SHOCK_POSITION:.3f} ± {_TOLERANCE:.3f}"
    )

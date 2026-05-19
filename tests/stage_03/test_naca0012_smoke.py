"""Stage 03 — NACA 0012 walking-skeleton smoke test.

Drives the full solver pipeline (prepare -> mesh -> solve -> load) against the
OpenFOAM SIF on aero-build and asserts the drag coefficient lands within
+/-25% of the Ladson reference (Cd ~= 0.0079).

Marked `slow` + `stage_03`: skipped unless `--run-slow` / `AERO_RUN_SLOW`, and
skipped cleanly when the cluster, SIF, or `aero[openfoam]` extra is absent.
The +/-25% band is a deliberately loose walking-skeleton tolerance; Stage 05
tightens it against NASA TMR data.

This test covers the *solver* contract only. The four-fold provenance logging
that Stage 04 added to `aero run` is exercised end-to-end by
`tests/stage_04/test_provenance_completeness.py`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REFERENCE_CD = 0.0079  # Ladson, NASA TM-4074
TOLERANCE = 0.25


def _nfs_roots() -> tuple[Path, Path]:
    if os.path.ismount("/mnt/aero-nfs"):
        return Path("/mnt/aero-nfs"), Path("/mnt/aero")
    return Path("/mnt/aero"), Path("/mnt/aero")


@pytest.mark.slow
@pytest.mark.stage_03
def test_naca0012_smoke(
    aero_build_reachable: bool,
    openfoam_sif_present: bool,
    openfoam_extra_installed: bool,
) -> None:
    if not aero_build_reachable:
        pytest.skip("aero-build not reachable over SSH")
    if not openfoam_sif_present:
        pytest.skip("openfoam-esi.sif not published on aero-build")
    if not openfoam_extra_installed:
        pytest.skip("aero[openfoam] extra not installed")

    from aero.adapters.openfoam import OpenFOAMSolver
    from aero.adapters.openfoam.schemas import CaseSpec
    from aero.orchestration import LocalSSHExecutor

    repo_root = Path(__file__).resolve().parents[2]
    host_root, remote_root = _nfs_roots()
    spec = CaseSpec(name="naca0012", reynolds=6.0e6, mach=0.15, aoa_deg=0.0)
    solver = OpenFOAMSolver(host_nfs_root=host_root, remote_nfs_root=remote_root)
    executor = LocalSSHExecutor(host="aero-build", ssh_user="root", repo_root=repo_root)

    case_dir = solver.prepare(spec)
    mesh = solver.mesh(case_dir, executor)
    assert mesh.ok, "blockMesh did not produce a polyMesh"

    result = solver.run(case_dir, executor)
    assert result.returncode == 0, f"simpleFoam failed (rc={result.returncode})"

    dataset = solver.load(result)
    cd = float(dataset.attrs["cd"])
    low, high = REFERENCE_CD * (1 - TOLERANCE), REFERENCE_CD * (1 + TOLERANCE)
    assert low <= cd <= high, f"Cd {cd:.5f} outside walking-skeleton band [{low:.5f}, {high:.5f}]"

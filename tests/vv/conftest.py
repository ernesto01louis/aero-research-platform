"""Fixtures for the cluster-bound V&V suite (slow tests).

The TMR cases run a real CFD solve on the aero cluster, log to MLflow, and
mirror provenance into Postgres — so the slow tests need SSH, the OpenFOAM
SIF, the `aero[openfoam,provenance,vv]` extras, a reachable MLflow server, and
`AERO_PROVENANCE_DSN`. `vv_cluster_ready` gates all of that; a slow test
skips cleanly when any piece is missing.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return _REPO_ROOT


@pytest.fixture(scope="session")
def vv_cluster_ready(
    aero_build_reachable: bool,
    openfoam_sif_present: bool,
    openfoam_extra_installed: bool,
) -> bool:
    """True iff a full V&V run can execute: cluster, extras, MLflow, Postgres DSN."""
    if not (aero_build_reachable and openfoam_sif_present and openfoam_extra_installed):
        return False
    if importlib.util.find_spec("scipy") is None:
        return False
    return bool(os.environ.get("AERO_PROVENANCE_DSN"))


@pytest.fixture(scope="session")
def vv_cluster_ready_su2(
    aero_build_reachable: bool,
    su2_sif_present: bool,
    su2_extra_installed: bool,
) -> bool:
    """True iff a full SU2 V&V run can execute (Stage 06)."""
    if not (aero_build_reachable and su2_sif_present and su2_extra_installed):
        return False
    if importlib.util.find_spec("scipy") is None:
        return False
    return bool(os.environ.get("AERO_PROVENANCE_DSN"))


def _runner(repo_root: Path, *, solver_name: str):  # type: ignore[no-untyped-def]
    """Construct a `BenchmarkRunner` + provenance-builder for `solver_name`."""
    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.adapters.su2.solver import SU2Solver
    from aero.orchestration import LocalSSHExecutor
    from aero.provenance import compute_provenance
    from aero.provenance.db import resolve_dsn
    from aero.vv import BenchmarkRunner

    nfs = Path("/mnt/aero-nfs") if os.path.ismount("/mnt/aero-nfs") else Path("/mnt/aero")
    solver: object
    if solver_name == "openfoam":
        solver = OpenFOAMSolver(host_nfs_root=nfs, remote_nfs_root=Path("/mnt/aero"))
        version = "OpenFOAM-ESI v2412"
        sif_name = "openfoam-esi.sif"
    elif solver_name == "su2":
        solver = SU2Solver(
            host_nfs_root=nfs, remote_nfs_root=Path("/mnt/aero"), repo_root=repo_root
        )
        version = "SU2 v8"
        sif_name = "su2-v8.sif"
    else:
        raise ValueError(f"unknown solver {solver_name!r}")

    executor = LocalSSHExecutor(host="aero-build", ssh_user="root", repo_root=repo_root)
    runner = BenchmarkRunner(
        solver=solver,  # type: ignore[arg-type]
        executor=executor,
        tracking_uri="http://192.168.2.234:5000",
        experiment="aero-provenance",
        db_dsn=resolve_dsn(),
        solver_version=version,
        stage="06" if solver_name == "su2" else "05",
    )

    def _provenance(spec: object) -> object:
        return compute_provenance(
            repo_root=repo_root,
            container_sif=sif_name,
            resolved_config=spec.model_dump(mode="json"),  # type: ignore[attr-defined]
            allow_dirty=True,
        )

    return runner, _provenance


@pytest.fixture
def vv_runner(repo_root: Path):  # type: ignore[no-untyped-def]
    """OpenFOAM `BenchmarkRunner` (Stage 05 default)."""
    return _runner(repo_root, solver_name="openfoam")


@pytest.fixture
def vv_runner_su2(repo_root: Path):  # type: ignore[no-untyped-def]
    """SU2 `BenchmarkRunner` (Stage 06)."""
    return _runner(repo_root, solver_name="su2")

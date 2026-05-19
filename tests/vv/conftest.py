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


@pytest.fixture
def vv_runner(repo_root: Path):  # type: ignore[no-untyped-def]
    """A `BenchmarkRunner` wired to the aero cluster, plus the provenance tuple."""
    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.orchestration import LocalSSHExecutor
    from aero.provenance import compute_provenance
    from aero.provenance.db import resolve_dsn
    from aero.vv import BenchmarkRunner

    nfs = Path("/mnt/aero-nfs") if os.path.ismount("/mnt/aero-nfs") else Path("/mnt/aero")
    solver = OpenFOAMSolver(host_nfs_root=nfs, remote_nfs_root=Path("/mnt/aero"))
    executor = LocalSSHExecutor(host="aero-build", ssh_user="root", repo_root=repo_root)
    runner = BenchmarkRunner(
        solver=solver,
        executor=executor,
        tracking_uri="http://192.168.2.234:5000",
        experiment="aero-provenance",
        db_dsn=resolve_dsn(),
        solver_version="OpenFOAM-ESI v2412",
        stage="05",
    )

    def _provenance(spec: object) -> object:
        return compute_provenance(
            repo_root=repo_root,
            container_sif="openfoam-esi.sif",
            resolved_config=spec.model_dump(mode="json"),  # type: ignore[attr-defined]
            allow_dirty=True,
        )

    return runner, _provenance

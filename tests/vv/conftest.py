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


@pytest.fixture(scope="session")
def vv_cluster_ready_pyfr(
    aero_build_reachable: bool,
    pyfr_sif_present: bool,
    pyfr_extra_installed: bool,
) -> bool:
    """True iff a full PyFR V&V run can execute (Stage 07).

    Note: this fixture only checks the LOCAL SSH path (PyFR over aero-build).
    The Stage-07 first paid GPU run goes through the RunPod executor and
    needs `RUNPOD_API_KEY` + `/etc/aero/runpod-ledger.json` instead; that
    integration test is gated by env var, not by this fixture.
    """
    if not (aero_build_reachable and pyfr_sif_present and pyfr_extra_installed):
        return False
    if importlib.util.find_spec("scipy") is None:
        return False
    return bool(os.environ.get("AERO_PROVENANCE_DSN"))


@pytest.fixture(scope="session")
def vv_cluster_ready_nekrs(
    aero_build_reachable: bool,
    nekrs_sif_present: bool,
    nekrs_extra_installed: bool,
) -> bool:
    """True iff a full NekRS V&V run can execute (Stage 07)."""
    if not (aero_build_reachable and nekrs_sif_present and nekrs_extra_installed):
        return False
    if importlib.util.find_spec("scipy") is None:
        return False
    return bool(os.environ.get("AERO_PROVENANCE_DSN"))


def _runner(repo_root: Path, *, solver_name: str):  # type: ignore[no-untyped-def]
    """Construct a `BenchmarkRunner` + provenance-builder for `solver_name`."""
    from aero.adapters.nekrs.solver import NekRSSolver
    from aero.adapters.openfoam.solver import OpenFOAMSolver
    from aero.adapters.pyfr.solver import PyFRSolver
    from aero.adapters.su2.solver import SU2Solver
    from aero.orchestration import LocalSSHExecutor
    from aero.provenance import compute_provenance
    from aero.provenance.db import resolve_dsn
    from aero.vv import BenchmarkRunner

    nfs = Path("/mnt/aero-nfs") if os.path.ismount("/mnt/aero-nfs") else Path("/mnt/aero")
    solver: object
    stage = "05"
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
        stage = "06"
    elif solver_name == "pyfr":
        solver = PyFRSolver(
            host_nfs_root=nfs, remote_nfs_root=Path("/mnt/aero"), repo_root=repo_root
        )
        version = "PyFR 1.15.0"
        sif_name = "pyfr.sif"
        stage = "07"
    elif solver_name == "nekrs":
        solver = NekRSSolver(
            host_nfs_root=nfs, remote_nfs_root=Path("/mnt/aero"), repo_root=repo_root
        )
        version = "NekRS v23.0"
        sif_name = "nekrs.sif"
        stage = "07"
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
        stage=stage,
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


@pytest.fixture
def vv_runner_pyfr(repo_root: Path):  # type: ignore[no-untyped-def]
    """PyFR `BenchmarkRunner` (Stage 07)."""
    return _runner(repo_root, solver_name="pyfr")


@pytest.fixture
def vv_runner_nekrs(repo_root: Path):  # type: ignore[no-untyped-def]
    """NekRS `BenchmarkRunner` (Stage 07)."""
    return _runner(repo_root, solver_name="nekrs")

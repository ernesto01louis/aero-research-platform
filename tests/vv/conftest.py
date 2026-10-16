"""Fixtures for the cluster-bound V&V suite (slow tests).

The TMR cases run a real CFD solve on the aero cluster, log to MLflow, and
mirror provenance into Postgres — so the slow tests need SSH, the OpenFOAM
SIF, the `aero[openfoam,provenance,vv]` extras, a reachable MLflow server, and
`AERO_PROVENANCE_DSN`. `vv_cluster_ready` gates all of that; a slow test
skips cleanly when any piece is missing.

In CI the cluster is not optional (Stage 22, ADR-051): the V&V jobs set
`AERO_VV_REQUIRE_CLUSTER=1`, and a readiness fixture then FAILS, naming the missing
pieces, instead of letting every test skip and the job go green having measured
nothing. `pytest_deselected` records what the `-m` selection left out, so the job
summary can say in words what was not measured and why (`scripts/vv_ci_summary.py`).
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Set by the V&V CI jobs: a cluster that is not ready is a failure there, not a skip.
_REQUIRE_CLUSTER = "AERO_VV_REQUIRE_CLUSTER"
#: Set by the V&V CI jobs: where `pytest_deselected` appends one JSON line per deselected test.
_DESELECTED_JSON = "AERO_VV_DESELECTED_JSON"


def _ready(stack: str, checks: dict[str, bool]) -> bool:
    """All `checks` pass; with `AERO_VV_REQUIRE_CLUSTER=1`, fail loudly naming the gaps."""
    missing = [name for name, ok in checks.items() if not ok]
    if missing and os.environ.get(_REQUIRE_CLUSTER) == "1":
        pytest.fail(
            f"{_REQUIRE_CLUSTER}=1 but the {stack} V&V cluster is not ready: missing "
            + ", ".join(missing)
            + ". A V&V job that cannot reach its cluster has measured nothing; it must not "
            "pass by skipping (Stage 22, ADR-051).",
            pytrace=False,
        )
    return not missing


def _base_checks(reachable: bool, sif: bool, extra: bool, sif_name: str) -> dict[str, bool]:
    return {
        "ssh root@aero-build": reachable,
        f"/opt/aero/containers/{sif_name} on aero-build": sif,
        "the solver extras (importable)": extra,
        "scipy (aero[vv])": importlib.util.find_spec("scipy") is not None,
        "AERO_PROVENANCE_DSN": bool(os.environ.get("AERO_PROVENANCE_DSN")),
    }


def pytest_deselected(items: list[pytest.Item]) -> None:
    """Record every deselected test with its markers and any `unmeasurable` reason."""
    dest = os.environ.get(_DESELECTED_JSON)
    if not dest:
        return
    with open(dest, "a", encoding="utf-8") as fh:
        for item in items:
            mark = item.get_closest_marker("unmeasurable")
            record = {
                "nodeid": item.nodeid,
                "markers": sorted({m.name for m in item.iter_markers()}),
                "reason": str(mark.kwargs.get("reason", "")) if mark else "",
            }
            fh.write(json.dumps(record) + "\n")


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
    return _ready(
        "OpenFOAM",
        _base_checks(
            aero_build_reachable, openfoam_sif_present, openfoam_extra_installed, "openfoam-esi.sif"
        ),
    )


@pytest.fixture(scope="session")
def vv_cluster_ready_su2(
    aero_build_reachable: bool,
    su2_sif_present: bool,
    su2_extra_installed: bool,
) -> bool:
    """True iff a full SU2 V&V run can execute (Stage 06)."""
    return _ready(
        "SU2",
        _base_checks(aero_build_reachable, su2_sif_present, su2_extra_installed, "su2-v8.sif"),
    )


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
    return _ready(
        "PyFR",
        _base_checks(aero_build_reachable, pyfr_sif_present, pyfr_extra_installed, "pyfr.sif"),
    )


@pytest.fixture(scope="session")
def vv_cluster_ready_nekrs(
    aero_build_reachable: bool,
    nekrs_sif_present: bool,
    nekrs_extra_installed: bool,
) -> bool:
    """True iff a full NekRS V&V run can execute (Stage 07)."""
    return _ready(
        "NekRS",
        _base_checks(aero_build_reachable, nekrs_sif_present, nekrs_extra_installed, "nekrs.sif"),
    )


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

"""Shared pytest fixtures and the slow-test gate.

The `slow` marker tags tests that need the aero LXC cluster (a real CFD run).
They are skipped unless `--run-slow` is passed or `AERO_RUN_SLOW` is set, so
the default `pytest` and the CI unit job stay fast and hermetic.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess

import pytest

_SSH = ("ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "root@aero-build")


def pytest_addoption(parser):
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="run slow tests (cluster CFD smoke tests)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-slow") or os.environ.get("AERO_RUN_SLOW"):
        return
    skip = pytest.mark.skip(reason="slow test — pass --run-slow or set AERO_RUN_SLOW")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)


def _ssh_ok(*remote: str) -> bool:
    if shutil.which("ssh") is None:
        return False
    try:
        proc = subprocess.run([*_SSH, *remote], capture_output=True, timeout=25)
    except (subprocess.SubprocessError, OSError):
        return False
    return proc.returncode == 0


@pytest.fixture(scope="session")
def aero_build_reachable() -> bool:
    """True iff `ssh root@aero-build` works without prompting."""
    return _ssh_ok("true")


@pytest.fixture(scope="session")
def openfoam_sif_present(aero_build_reachable: bool) -> bool:
    """True iff the OpenFOAM SIF is published on aero-build."""
    return aero_build_reachable and _ssh_ok("test", "-f", "/opt/aero/containers/openfoam-esi.sif")


@pytest.fixture(scope="session")
def openfoam_extra_installed() -> bool:
    """True iff the `aero[openfoam]` runtime dependencies are importable."""
    return all(importlib.util.find_spec(m) is not None for m in ("xarray", "mlflow"))


@pytest.fixture(scope="session")
def su2_sif_present(aero_build_reachable: bool) -> bool:
    """True iff the SU2 SIF is published on aero-build (Stage 06)."""
    return aero_build_reachable and _ssh_ok("test", "-f", "/opt/aero/containers/su2-v8.sif")


@pytest.fixture(scope="session")
def su2_extra_installed() -> bool:
    """True iff the `aero[su2]` host-side dependencies are importable (Stage 06)."""
    # `aero[su2]` is intentionally light host-side; mlflow comes from `provenance`.
    return importlib.util.find_spec("mlflow") is not None


@pytest.fixture(scope="session")
def pyfr_sif_present(aero_build_reachable: bool) -> bool:
    """True iff the PyFR SIF is published on aero-build (Stage 07)."""
    return aero_build_reachable and _ssh_ok("test", "-f", "/opt/aero/containers/pyfr.sif")


@pytest.fixture(scope="session")
def pyfr_extra_installed() -> bool:
    """True iff `aero[pyfr]` host-side deps + provenance MLflow are importable (Stage 07)."""
    return all(importlib.util.find_spec(m) is not None for m in ("h5py", "mako", "mlflow"))


@pytest.fixture(scope="session")
def nekrs_sif_present(aero_build_reachable: bool) -> bool:
    """True iff the NekRS SIF is published on aero-build (Stage 07)."""
    return aero_build_reachable and _ssh_ok("test", "-f", "/opt/aero/containers/nekrs.sif")


@pytest.fixture(scope="session")
def nekrs_extra_installed() -> bool:
    """True iff `aero[nekrs]` host-side deps + provenance MLflow are importable (Stage 07)."""
    return all(importlib.util.find_spec(m) is not None for m in ("meshio", "mlflow"))


@pytest.fixture(scope="session")
def jax_fluids_sif_present(aero_build_reachable: bool) -> bool:
    """True iff the JAX-Fluids SIF is published on aero-build (Stage 08)."""
    return aero_build_reachable and _ssh_ok("test", "-f", "/opt/aero/containers/jax-fluids.sif")


@pytest.fixture(scope="session")
def jax_fluids_extra_installed() -> bool:
    """True iff `aero[jax-fluids]` host-side deps are importable (Stage 08).

    Host-side the adapter only requires h5py + the provenance MLflow stack;
    jax / jaxlib / jaxfluids live in the SIF (or in-process on aero-dev for
    the differentiable_run path, opted into by the operator).
    """
    return all(importlib.util.find_spec(m) is not None for m in ("h5py", "mlflow"))


@pytest.fixture(scope="session")
def surrogate_smoke_sif_present(aero_build_reachable: bool) -> bool:
    """True iff the surrogate-smoke SIF is published on aero-build (Stage 08)."""
    return aero_build_reachable and _ssh_ok(
        "test", "-f", "/opt/aero/containers/surrogate-smoke.sif"
    )


@pytest.fixture(scope="session")
def surrogate_smoke_extra_installed() -> bool:
    """True iff `aero[surrogate-smoke]` deps are importable host-side (Stage 08).

    The three Stage-08 baselines need torch + torch-geometric + mlflow + numpy
    for their fit/predict paths; without all four the tests skip.
    """
    return all(
        importlib.util.find_spec(m) is not None
        for m in ("torch", "torch_geometric", "mlflow", "numpy", "einops")
    )

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

"""Stage 04 — PLATFORM-NOT-HUB invariant guard.

`import aero` and `import aero.provenance` must not pull in any heavy extra
dependency. Verified in a fresh interpreter so the result is independent of
what the test session has already imported. Run in the default CI suite.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.stage_04

# Modules behind the openfoam / provenance extras — none may load as a
# side effect of importing the aero core.
_HEAVY = ("mlflow", "hydra", "omegaconf", "psycopg2", "boto3", "xarray", "dvc")


def _imports_clean(module: str) -> subprocess.CompletedProcess[str]:
    code = (
        f"import {module}; import sys; "
        f"leaked = [m for m in {_HEAVY!r} if m in sys.modules]; "
        "assert not leaked, leaked; print('ok')"
    )
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)


def test_import_aero_core_is_lightweight() -> None:
    result = _imports_clean("aero")
    assert result.returncode == 0, result.stderr


def test_import_aero_provenance_is_lightweight() -> None:
    result = _imports_clean("aero.provenance")
    assert result.returncode == 0, result.stderr


def test_import_four_fold_is_lightweight() -> None:
    result = _imports_clean("aero.provenance.four_fold")
    assert result.returncode == 0, result.stderr

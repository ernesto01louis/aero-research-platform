"""PLATFORM-NOT-HUB, measured: the reportable surface imports with ONLY stdlib + numpy + pydantic.

Hard Rule 1 says the ``aero/`` core imports only stdlib + numpy + pydantic. The
``import-platform-only`` CI job cannot see a violation by a *base* dependency (it installs
loguru, typer and dvc), and until Stage 21 ``aero.vv.reportable`` could not be imported without
loguru: ``aero/vv/__init__.py`` -> ``aero/vv/_base.py`` -> ``aero/adapters/_base.py`` imported it
at module level, as did ``aero/orchestration/local_ssh.py`` (ADR-049 H-12). The result-crate
reader (ADR-047) is built on this surface and must run on a machine that has nothing else.

Each module is imported in a fresh ``python -I`` subprocess behind a meta-path finder that
refuses every top-level package outside the standard library and the pydantic/numpy closure,
then checked for forbidden modules having loaded anyway.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap

import pytest

pytestmark = pytest.mark.stage_21

CORE_MODULES = (
    "aero.provenance.four_fold",
    "aero.vv.statistical_uncertainty",
    "aero.vv.paired_difference",
    "aero.vv.reportable",
    "aero.vv.reportable_compose",
    "aero.surrogates._common.certificate",
    # Stage 22: the production gate's typed status, stack table and MLflow read. The report
    # takes its client as a parameter, so it must load no mlflow of its own.
    "aero.vv.status",
    "aero.vv.stacks",
    "aero.vv.report",
    # Stage 23 (ADR-052): the declared-input parser and the one read path; no yaml, no dvc.
    "aero.provenance.dvc_inputs",
)

# Present in a full dev install, so their ABSENCE from sys.modules is the real assertion.
MUST_NOT_LOAD = ("loguru", "typer", "click", "dvc", "scipy", "mlflow", "rich", "yaml")

_PROBE = textwrap.dedent(
    """
    import importlib.abc, json, sys
    ALLOWED = set(sys.stdlib_module_names) | {
        "numpy", "pydantic", "pydantic_core", "annotated_types",
        "typing_extensions", "typing_inspection", "aero",
    }

    class Block(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            top = name.split(".")[0]
            if top in ALLOWED or top.startswith("_sysconfigdata"):
                return None
            raise ModuleNotFoundError(f"blocked by the PLATFORM-NOT-HUB probe: {name}")

    sys.meta_path.insert(0, Block())
    __import__(sys.argv[1])
    print(json.dumps(sorted(sys.modules)))
    """
)


@pytest.mark.parametrize("module", CORE_MODULES)
def test_core_module_imports_with_stdlib_numpy_pydantic_only(module: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-I", "-c", _PROBE, module],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, (
        f"{module} needs a module outside stdlib+numpy+pydantic:\n{proc.stderr}"
    )
    loaded = set(json.loads(proc.stdout.strip().splitlines()[-1]))
    leaked = sorted(m for m in MUST_NOT_LOAD if m in loaded)
    assert not leaked, f"importing {module} loaded {leaked}"
    assert "aero.optimize" not in loaded and "aero.cli" not in loaded

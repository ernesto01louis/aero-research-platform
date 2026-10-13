"""A crate verifies in an interpreter that can import NOTHING but stdlib + numpy + pydantic.

That is the clean-machine property (Hard Rule 16; ADR-047), proven in-process: the four
synthetic crates are written to disk, then verified, and their numbers extracted, in a fresh
``python -I`` subprocess behind a meta-path finder that refuses every other top-level package.
The CI round-trip job proves the same thing at the packaging level: a wheel installed with
``--no-deps`` beside numpy and pydantic only.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from aero.crate import verify_members, write_crate

from tests.unit._crate_fixtures import SHAPES, built

pytestmark = pytest.mark.stage_21

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
            raise ModuleNotFoundError(f"blocked by the clean-machine probe: {name}")

    sys.meta_path.insert(0, Block())
    from aero.crate import verify_crate
    out = {p: verify_crate(p).numbers() for p in sys.argv[1:]}
    print(json.dumps({"numbers": out, "modules": sorted(sys.modules)}))
    """
)

MUST_NOT_LOAD = (
    "loguru",
    "typer",
    "click",
    "dvc",
    "scipy",
    "mlflow",
    "rich",
    "yaml",
    "aero.optimize",
    "aero.cli",
)


def test_crates_verify_with_stdlib_numpy_pydantic_only(tmp_path: Path) -> None:
    paths = []
    expected = {}
    for shape in sorted(SHAPES):
        members = built(shape)
        dest = tmp_path / shape
        write_crate(dest, members)
        paths.append(str(dest))
        expected[str(dest)] = verify_members(members).numbers()
    proc = subprocess.run(
        [sys.executable, "-I", "-c", _PROBE, *paths],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout.strip().splitlines()[-1])
    assert report["numbers"] == expected
    loaded = set(report["modules"])
    leaked = sorted(m for m in MUST_NOT_LOAD if m in loaded)
    assert not leaked, f"the crate reader loaded {leaked}"

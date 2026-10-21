"""`--no-home` is a structural flag of `build_apptainer_exec` (Stage 23, ADR-053).

Three callers used to splice it in with `str.replace("apptainer exec ", "apptainer exec
--no-home ", 1)`, which rewrites the FIRST occurrence: a guard prefix containing that literal
would have moved the splice. The flag must produce exactly the bytes the splice produced.
"""

from __future__ import annotations

import pytest
from aero.adapters._base import build_apptainer_exec

pytestmark = pytest.mark.stage_23


@pytest.mark.parametrize("writable_tmpfs", [False, True])
@pytest.mark.parametrize("gpu", [False, True])
def test_the_flag_reproduces_the_old_splice_byte_for_byte(writable_tmpfs: bool, gpu: bool) -> None:
    kwargs = {
        "sif_path": "/opt/aero/containers/precice-fsi.sif",
        "case_bind_source": "/mnt/aero/runs/x",
        "command": "blockMesh",
        "writable_tmpfs": writable_tmpfs,
        "gpu": gpu,
    }
    spliced = build_apptainer_exec(**kwargs).replace(  # type: ignore[arg-type]
        "apptainer exec ", "apptainer exec --no-home ", 1
    )
    assert build_apptainer_exec(**kwargs, no_home=True) == spliced  # type: ignore[arg-type]
    assert build_apptainer_exec(**kwargs).count("--no-home") == 0  # type: ignore[arg-type]

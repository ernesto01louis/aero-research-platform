"""`PreciceCoupledSolver.decompose` — the parallel seam's other half (ADR-040 L4).

`mesh()` runs `blockMesh` as the container root, which is harmless: `constant/polyMesh`
is only read afterwards. `decomposePar` WRITES `processor*/`, and `pimpleFoam` then writes
into those directories every time step — root-owned, the solve dies at t=0. So the two
utilities must not be launched the same way, and the tests here pin the difference.

The second property is the one that costs a wave rather than a minute: `decomposePar`
exits **0** having produced fewer subdomains than requested. A run whose decomposition
nobody counted is a different configuration wearing the pre-registered one's clothes, and
its seconds-per-window is not the number B2 was sized on.

In `tests/unit/` because `tests/stage_20` is not in CI (handoff §6.24).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aero.adapters._base import CaseDir
from aero.adapters.openfoam._foam_common import decompose_par_dict
from aero.adapters.precice.case import CASE_ROOT_DIRNAME
from aero.adapters.precice.solver import PreciceCoupledSolver
from aero.orchestration._base import ExecResult
from aero.vv.fsi.hg2007_flexible_foil import hg2007_case_spec

pytestmark = pytest.mark.stage_20

_DT = 2.0e-5
_MAX_TIME = 0.01


class _FakeExecutor:
    """Records the command and reports a scripted returncode; writes nothing."""

    def __init__(self, returncode: int = 0) -> None:
        self.commands: list[str] = []
        self._returncode = returncode

    def run(self, command: str, **kwargs: Any) -> ExecResult:
        self.commands.append(command)
        return ExecResult(
            command=command,
            returncode=self._returncode,
            stdout="",
            stderr="" if self._returncode == 0 else "decomposePar: boom",
            duration_s=1.0,
            host="fake",
        )


def _case_dir(tmp_path: Path) -> CaseDir:
    spec = hg2007_case_spec(
        arm="flexible",
        rung="mid",
        time_window_size=_DT,
        max_time=_MAX_TIME,
        wall_clock_ceiling_s=3600,
    )
    return CaseDir(
        run_id="hg2007_flexible_foil-decompose-test",
        spec=spec,
        host_path=tmp_path / "run",
        remote_path=Path("/mnt/aero/runs/hg2007_flexible_foil-decompose-test"),
    )


def _fluid_dir(case_dir: CaseDir, tmp_path: Path) -> Path:
    spec = case_dir.spec
    return (
        tmp_path
        / "run"
        / CASE_ROOT_DIRNAME
        / spec.case_subdir  # type: ignore[union-attr]
        / spec.fluid_participant_dir  # type: ignore[union-attr]
    )


def _make_processor_dirs(root: Path, n: int) -> None:
    for i in range(n):
        (root / f"processor{i}").mkdir(parents=True, exist_ok=True)


def test_decompose_runs_under_the_participant_uid_and_not_under_mpirun(tmp_path: Path) -> None:
    case_dir = _case_dir(tmp_path)
    _make_processor_dirs(_fluid_dir(case_dir, tmp_path), 4)
    executor = _FakeExecutor()

    report = PreciceCoupledSolver().decompose(case_dir, executor, ranks=4)  # type: ignore[arg-type]

    (command,) = executor.commands
    # UNDER THE UID: pimpleFoam writes into processor*/, and root-owned ones kill t=0.
    assert "setpriv --reuid=1000 --regid=1000" in command
    # SERIAL: decomposePar has no -parallel, and mpirun as root is refused outright.
    assert "mpirun" not in command
    assert "decomposePar -force" in command
    # In the fluid participant's own directory, prefixed the way launch_plan prefixes it.
    assert "cd hg2007-flexible-foil/fluid-openfoam && decomposePar -force" in command
    assert report.ok
    assert (report.ranks_requested, report.n_processor_dirs) == (4, 4)


def test_a_silent_fallback_to_fewer_subdomains_is_refused(tmp_path: Path) -> None:
    """The measured failure mode: exit 0, fewer processor* directories than asked for."""
    case_dir = _case_dir(tmp_path)
    _make_processor_dirs(_fluid_dir(case_dir, tmp_path), 2)

    report = PreciceCoupledSolver().decompose(
        case_dir,
        _FakeExecutor(returncode=0),  # type: ignore[arg-type]
        ranks=4,
    )

    assert not report.ok
    assert report.n_processor_dirs == 2
    assert "wrote 2 processor* directories" in report.failure
    assert "different configuration" in report.failure


def test_a_nonzero_decompose_is_a_failure_even_with_the_right_directory_count(
    tmp_path: Path,
) -> None:
    """Stale `processor*` from a previous pass must not launder a failed decomposition."""
    case_dir = _case_dir(tmp_path)
    _make_processor_dirs(_fluid_dir(case_dir, tmp_path), 4)

    report = PreciceCoupledSolver().decompose(
        case_dir,
        _FakeExecutor(returncode=1),  # type: ignore[arg-type]
        ranks=4,
    )

    assert not report.ok
    assert report.n_processor_dirs == 4


def test_decompose_refuses_a_rank_count_below_one(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ranks must be >= 1"):
        PreciceCoupledSolver().decompose(
            _case_dir(tmp_path),
            _FakeExecutor(),  # type: ignore[arg-type]
            ranks=0,
        )


def test_the_decompose_par_dict_is_a_pure_function_of_the_rank_count() -> None:
    """`scotch` needs no geometry hints, so the dictionary cannot drift from the mesh."""
    rendered = decompose_par_dict(4)
    assert "numberOfSubdomains 4;" in rendered
    assert "method          scotch;" in rendered
    assert rendered.startswith("/*----")
    assert "object      decomposeParDict;" in rendered
    assert decompose_par_dict(4) != decompose_par_dict(6)
    with pytest.raises(ValueError, match="ranks must be >= 1"):
        decompose_par_dict(0)

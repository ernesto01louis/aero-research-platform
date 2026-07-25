"""aero.adapters.openfoam.robust_mesh — ladder descent, records, loud exhaustion.

Drives `mesh_with_ladder` with fake solver/executor doubles: a rung whose mesh dies,
a rung failing the gate, a rung passing — every attempt recorded; exhaustion raises
GeometryError carrying the full report; the gate object is never rebuilt (F4).
Stage 18, ADR-034.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from aero.adapters._base import CaseDir, MeshHandle
from aero.adapters.openfoam.external_geometry import ExternalGeometrySpec
from aero.adapters.openfoam.robust_mesh import (
    DEFAULT_LADDER,
    MeshLadderRung,
    mesh_with_ladder,
)
from aero.geometry import GeometryError, write_stl
from aero.orchestration._base import ExecResult

from tests.unit.geometry_fixtures import cube

_CHECKMESH_PASS = """
Mesh stats
    cells:            41208
Checking geometry...
    Max aspect ratio = 3.4 OK.
    Min volume = 1.2e-08. Max volume = 1.3e-07.  Total volume = 0.005.  Cell volumes OK.
    Mesh non-orthogonality Max: 52.3 average: 8.1
    Max skewness = 1.9 OK.
Mesh OK.
End
"""

_CHECKMESH_FAIL = """
Mesh stats
    cells:            41000
Checking geometry...
    Max aspect ratio = 40.0 OK.
    Min volume = 1e-11. Max volume = 1e-07.  Total volume = 0.005.  Cell volumes OK.
    Mesh non-orthogonality Max: 79.5 average: 12.0
 ***Max skewness = 6.2, highly skew faces detected
Failed 1 mesh checks.
End
"""


def _spec(tmp_path: Path) -> ExternalGeometrySpec:
    stl = tmp_path / "body.stl"
    write_stl(cube(), stl)
    return ExternalGeometrySpec(
        name="ladder-test",
        surface_source=str(stl),
        surface_sha256=hashlib.sha256(stl.read_bytes()).hexdigest(),
    )


class _FakeSolver:
    """SolverProtocol double: `mesh_ok_plan` scripts each rung's mesh outcome."""

    def __init__(self, tmp_path: Path, mesh_ok_plan: list[bool]) -> None:
        self._tmp = tmp_path
        self._plan = mesh_ok_plan
        self._calls = 0
        self.prepared_specs: list[ExternalGeometrySpec] = []

    def prepare(self, case: Any) -> CaseDir:
        self.prepared_specs.append(case)
        run_id = f"{case.name}-{len(self.prepared_specs):04d}"
        return CaseDir(
            run_id=run_id,
            spec=case,
            host_path=self._tmp / run_id,
            remote_path=Path("/mnt/aero/runs") / run_id,
        )

    def mesh(self, case_dir: CaseDir, executor: Any) -> MeshHandle:
        ok = self._plan[self._calls]
        self._calls += 1
        return MeshHandle(case_dir=case_dir, ok=ok, n_elements=41208 if ok else None)

    def run(self, case_dir: Any, executor: Any) -> Any:  # pragma: no cover — protocol
        raise NotImplementedError

    def load(self, result: Any) -> Any:  # pragma: no cover — protocol
        raise NotImplementedError

    def wall_distribution(self, result: Any, *, patch: str, u_inf: float = 1.0) -> Any:
        raise NotImplementedError  # pragma: no cover — protocol


class _FakeExecutor:
    """Executor double returning scripted checkMesh stdout per call."""

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = outputs
        self._calls = 0

    def run(self, command: str, **kwargs: Any) -> ExecResult:
        out = self._outputs[self._calls]
        self._calls += 1
        return ExecResult(command=command, returncode=0, stdout=out, duration_s=1.0, host="fake")


def test_first_passing_rung_wins_and_all_attempts_recorded(tmp_path: Path) -> None:
    solver = _FakeSolver(tmp_path, mesh_ok_plan=[False, True, True])
    executor = _FakeExecutor([_CHECKMESH_FAIL, _CHECKMESH_PASS])
    case_dir, handle, report = mesh_with_ladder(
        solver=solver,  # type: ignore[arg-type]
        executor=executor,  # type: ignore[arg-type]
        spec=_spec(tmp_path),
        sif_path=Path("/opt/aero/containers/openfoam-esi.sif"),
    )
    # R0 mesh died, R1 meshed but failed the gate, R2 passed.
    assert report.passed_rung == "R2"
    assert [a.rung.name for a in report.attempts] == ["R0", "R1", "R2"]
    assert [a.passed for a in report.attempts] == [False, False, True]
    assert report.attempts[0].mesh_completed is False and report.attempts[0].gate is None
    assert report.attempts[1].gate is not None and not report.attempts[1].gate.passed
    assert handle.ok
    assert case_dir.run_id.startswith("ladder-test-r2")


def test_rung_specs_degrade_cost_never_thresholds(tmp_path: Path) -> None:
    solver = _FakeSolver(tmp_path, mesh_ok_plan=[True, True, True])
    executor = _FakeExecutor([_CHECKMESH_PASS])
    spec = _spec(tmp_path)
    mesh_with_ladder(
        solver=solver,  # type: ignore[arg-type]
        executor=executor,  # type: ignore[arg-type]
        spec=spec,
        sif_path=Path("/opt/aero/containers/openfoam-esi.sif"),
    )
    r0 = solver.prepared_specs[0]
    assert r0.base_cell_size == spec.base_cell_size  # R0 = target resolution
    assert r0.n_surface_layers == DEFAULT_LADDER[0].n_surface_layers


def test_exhausted_ladder_raises_with_full_report(tmp_path: Path) -> None:
    solver = _FakeSolver(tmp_path, mesh_ok_plan=[True, True, True])
    executor = _FakeExecutor([_CHECKMESH_FAIL, _CHECKMESH_FAIL, _CHECKMESH_FAIL])
    with pytest.raises(GeometryError, match="ladder exhausted") as excinfo:
        mesh_with_ladder(
            solver=solver,  # type: ignore[arg-type]
            executor=executor,  # type: ignore[arg-type]
            spec=_spec(tmp_path),
            sif_path=Path("/opt/aero/containers/openfoam-esi.sif"),
        )
    report = excinfo.value.ladder_report  # type: ignore[attr-defined]
    assert report.passed_rung is None
    assert len(report.attempts) == 3
    assert "thresholds were never relaxed" in str(excinfo.value)


def test_custom_single_rung_ladder(tmp_path: Path) -> None:
    solver = _FakeSolver(tmp_path, mesh_ok_plan=[True])
    executor = _FakeExecutor([_CHECKMESH_PASS])
    rung = MeshLadderRung(name="only", cell_size_factor=2.0, n_surface_layers=0)
    _, _, report = mesh_with_ladder(
        solver=solver,  # type: ignore[arg-type]
        executor=executor,  # type: ignore[arg-type]
        spec=_spec(tmp_path),
        sif_path=Path("/opt/aero/containers/openfoam-esi.sif"),
        rungs=(rung,),
    )
    assert report.passed_rung == "only"
    assert solver.prepared_specs[0].base_cell_size == pytest.approx(0.01)

"""Unit tests for the PyFR adapter — Stage 07.

These tests cover the host-side surface area (specs, case-writer, the
SolverProtocol structural check). The cluster-bound `pyfr run` exercise
is in `tests/vv/test_taylor_green_pyfr.py` (slow, gated on the SIF +
RUNPOD env vars).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters._base import (
    SolverProtocol,
    build_apptainer_exec,
)
from aero.adapters._meshing.gmsh_high_order import (
    PERIODIC_FACE_TAGS,
    write_taylor_green_msh2,
)
from aero.adapters.pyfr import PyFRSolver, PyFRTaylorGreenSpec
from aero.adapters.pyfr.case_writer import write_taylor_green_ini

pytestmark = pytest.mark.stage_07


def test_pyfr_solver_satisfies_solver_protocol() -> None:
    solver = PyFRSolver(sif_path="/dev/null")
    assert isinstance(solver, SolverProtocol)


def test_pyfr_taylor_green_spec_defaults_are_workshop_canonical() -> None:
    spec = PyFRTaylorGreenSpec(name="tg")
    assert spec.reynolds == 1600.0
    assert spec.n_elements_per_dir == 32
    assert spec.polynomial_order == 3
    assert spec.t_end == 20.0
    assert spec.backend == "cuda"


def test_pyfr_spec_rejects_unknown_backend() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="Input should be"):
        PyFRTaylorGreenSpec(name="tg", backend="vulkan")  # type: ignore[arg-type]


def test_pyfr_spec_polynomial_order_in_2_to_6() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PyFRTaylorGreenSpec(name="tg", polynomial_order=1)
    with pytest.raises(ValidationError):
        PyFRTaylorGreenSpec(name="tg", polynomial_order=7)


def test_taylor_green_mesh_writer_emits_hex_count_and_periodic_faces(tmp_path: Path) -> None:
    """The structured TG mesh has n^3 hex elements + 6n^2 periodic quads."""
    mesh = tmp_path / "tg.msh2"
    n_hex = write_taylor_green_msh2(mesh, n_elements_per_dir=4)
    assert n_hex == 4**3
    text = mesh.read_text(encoding="utf-8")
    # Header
    assert text.startswith("$MeshFormat\n2.2 0 8\n$EndMeshFormat")
    # All six periodic faces declared as physical surfaces
    for name in PERIODIC_FACE_TAGS:
        assert f'"{name}"' in text
    # Elements section has 64 hex + 6*16 quad = 160 elements
    assert "$Elements\n160\n" in text


def test_taylor_green_mesh_writer_rejects_degenerate_input(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="n_elements_per_dir must be >= 2"):
        write_taylor_green_msh2(tmp_path / "x.msh2", n_elements_per_dir=1)
    with pytest.raises(ValueError, match="domain_half_extent must be > 0"):
        write_taylor_green_msh2(tmp_path / "x.msh2", n_elements_per_dir=4, domain_half_extent=-1.0)


def test_taylor_green_ini_writer_emits_periodic_bcs(tmp_path: Path) -> None:
    spec = PyFRTaylorGreenSpec(name="tg", n_elements_per_dir=8, polynomial_order=3)
    out = tmp_path / "solver.ini"
    write_taylor_green_ini(out, spec)
    ini = out.read_text(encoding="utf-8")
    # All six periodic BC blocks present
    for face in PERIODIC_FACE_TAGS:
        assert f"[soln-bcs-{face}]" in ini
        assert f"periodic-{face.split('_')[0]}" in ini
    # CUDA backend block + the Taylor-Green IC
    assert "[backend-cuda]" in ini
    assert "sin(x) * cos(y) * cos(z)" in ini


def test_pyfr_solver_write_case_creates_msh_and_ini(tmp_path: Path) -> None:
    solver = PyFRSolver(sif_path="/dev/null", host_nfs_root=tmp_path)
    # Use the smallest valid n_elements_per_dir (Field ge=8) to keep the test fast.
    spec = PyFRTaylorGreenSpec(name="tg-tw", n_elements_per_dir=8)
    case_dir = solver.prepare(spec)
    assert (case_dir.host_path / "mesh.msh2").is_file()
    assert (case_dir.host_path / "solver.ini").is_file()
    assert (case_dir.host_path / "out").is_dir()


def test_pyfr_solver_write_case_rejects_wrong_spec(tmp_path: Path) -> None:
    """The dispatcher fails loud on an unknown spec type (FAIL-LOUD / Invariant 2)."""
    solver = PyFRSolver(sif_path="/dev/null", host_nfs_root=tmp_path)

    class _Foreign:
        name = "x"

    with pytest.raises(TypeError, match="cannot handle spec"):
        solver._write_case(_Foreign(), tmp_path)


def test_pyfr_wall_distribution_raises_for_periodic_case(tmp_path: Path) -> None:
    """Taylor-Green has no wall; wall_distribution must fail loud."""
    from aero.adapters._base import CaseDir, ResultHandle

    solver = PyFRSolver(sif_path="/dev/null", host_nfs_root=tmp_path)
    case_dir = CaseDir(
        run_id="t",
        spec=PyFRTaylorGreenSpec(name="tg"),
        host_path=tmp_path,
        remote_path=Path("/mnt/aero/test"),
    )
    result = ResultHandle(case_dir=case_dir, returncode=0, output_host_path=tmp_path)
    with pytest.raises(NotImplementedError, match="periodic"):
        solver.wall_distribution(result, patch="wall")


def test_pyfr_apptainer_command_carries_gpu_and_backend(tmp_path: Path) -> None:
    """The compose path emits `apptainer exec --nv ... pyfr run -b cuda ...`."""
    cmd = build_apptainer_exec(
        sif_path="/opt/aero/containers/pyfr.sif",
        case_bind_source="/mnt/aero/runs/tg-test",
        command="pyfr run -b cuda -p solver.ini mesh.pyfrm",
        gpu=True,
        writable_tmpfs=True,
    )
    assert "--nv" in cmd
    assert "--writable-tmpfs" in cmd
    assert "pyfr run -b cuda" in cmd


def test_periodic_face_tags_distinct() -> None:
    """All six periodic face physical-group tags are unique."""
    assert len(set(PERIODIC_FACE_TAGS.values())) == 6

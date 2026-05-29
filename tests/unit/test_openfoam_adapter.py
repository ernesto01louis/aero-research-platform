"""Stage 03 unit tests for the OpenFOAM adapter — pure, no cluster or SSH.

Covers the pieces that must be correct before any cluster run: the analytic
geometry, the OpenFOAM case writer, the `apptainer exec` command builder, and
the solver's command construction (exercised through a fake `Executor`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.openfoam.case_writer import write_case
from aero.adapters.openfoam.geometry import naca0012_coordinates
from aero.adapters.openfoam.schemas import CaseSpec
from aero.adapters.openfoam.solver import OpenFOAMSolver, build_apptainer_exec
from aero.orchestration import ExecResult


def _spec(**overrides: object) -> CaseSpec:
    base = {"name": "naca0012", "reynolds": 6.0e6, "mach": 0.15, "aoa_deg": 0.0}
    return CaseSpec(**{**base, **overrides})  # type: ignore[arg-type]


# --- build_apptainer_exec -----------------------------------------------------
def test_build_apptainer_exec_exact_command() -> None:
    cmd = build_apptainer_exec(
        sif_path="/opt/aero/containers/openfoam-esi.sif",
        case_bind_source="/mnt/aero/runs/r1",
        command="blockMesh",
    )
    assert cmd == (
        "apptainer exec --bind /mnt/aero/runs/r1:/case "
        "/opt/aero/containers/openfoam-esi.sif bash -lc 'cd /case && blockMesh'"
    )


def test_build_apptainer_exec_quotes_paths_with_spaces() -> None:
    cmd = build_apptainer_exec(
        sif_path="/opt/aero/containers/openfoam-esi.sif",
        case_bind_source="/mnt/aero/runs/r 1",
        command="simpleFoam",
    )
    assert "'/mnt/aero/runs/r 1':/case" in cmd
    assert cmd.endswith("'cd /case && simpleFoam'")


# --- geometry -----------------------------------------------------------------
def test_naca0012_endpoints_on_chord_line() -> None:
    coords = naca0012_coordinates(80)
    assert tuple(coords[0]) == (0.0, 0.0)  # leading edge
    assert abs(coords[-1, 0] - 1.0) < 1e-9
    assert coords[-1, 1] == 0.0  # trailing edge closed to a point


def test_naca0012_max_thickness_is_twelve_percent() -> None:
    coords = naca0012_coordinates(400)
    assert 0.058 < float(coords[:, 1].max()) < 0.061  # half-thickness ~ 0.06


def test_naca0012_honours_point_count_and_scales_with_chord() -> None:
    assert len(naca0012_coordinates(57)) == 57
    scaled = naca0012_coordinates(80, chord=2.0)
    assert abs(scaled[-1, 0] - 2.0) < 1e-9


def test_naca0012_rejects_degenerate_count() -> None:
    with pytest.raises(ValueError, match="n_points"):
        naca0012_coordinates(1)


# --- case writer --------------------------------------------------------------
def test_write_case_produces_full_openfoam_tree(tmp_path: Path) -> None:
    write_case(_spec(), tmp_path)
    for rel in (
        "system/blockMeshDict",
        "system/controlDict",
        "system/fvSchemes",
        "system/fvSolution",
        "constant/transportProperties",
        "constant/turbulenceProperties",
        "0/U",
        "0/p",
        "0/k",
        "0/omega",
        "0/nut",
    ):
        assert (tmp_path / rel).is_file(), f"missing {rel}"


def test_blockmeshdict_is_an_eight_block_cgrid(tmp_path: Path) -> None:
    write_case(_spec(), tmp_path)
    text = (tmp_path / "system" / "blockMeshDict").read_text(encoding="utf-8")
    # Stage-05 C-grid: 8 blocks (UF/UA1/UA2/UW + lower mirror), 32 vertices,
    # 8 polyLine surface edges (4 at z=0, 4 at z=span), no `arc` (rectangular
    # far field, not a circle), no mergePatchPairs.
    assert text.count("hex (") == 8
    assert text.count("polyLine") == 8
    assert "arc " not in text
    assert "mergePatchPairs ( );" in text
    for patch in ("airfoil", "farfield", "front", "back"):
        assert patch in text


def test_blockmeshdict_far_field_scales_with_extent(tmp_path: Path) -> None:
    write_case(_spec(farfield_extent_chords=100.0), tmp_path)
    text = (tmp_path / "system" / "blockMeshDict").read_text(encoding="utf-8")
    # The rectangular far field sits at +/- the extent (chord 1.0 here).
    assert "100.00000000" in text


def test_controldict_requests_forcecoeffs(tmp_path: Path) -> None:
    write_case(_spec(), tmp_path)
    text = (tmp_path / "system" / "controlDict").read_text(encoding="utf-8")
    assert "application     simpleFoam;" in text
    assert "forceCoeffs" in text


def test_turbulence_model_is_komega_sst(tmp_path: Path) -> None:
    write_case(_spec(), tmp_path)
    text = (tmp_path / "constant" / "turbulenceProperties").read_text(encoding="utf-8")
    assert "kOmegaSST" in text


# --- solver command construction (fake executor) ------------------------------
class _FakeExecutor:
    """Records commands and returns a canned successful `ExecResult`."""

    def __init__(self, stdout: str = "") -> None:
        self.commands: list[str] = []
        self._stdout = stdout

    def run(
        self,
        command: str,
        *,
        timeout_s: int | None = None,
        long_running: bool = False,
        session: str | None = None,
    ) -> ExecResult:
        self.commands.append(command)
        return ExecResult(
            command=command,
            returncode=0,
            stdout=self._stdout,
            stderr="",
            duration_s=0.0,
            host="fake",
        )


def test_solver_mesh_builds_blockmesh_command(tmp_path: Path) -> None:
    solver = OpenFOAMSolver(
        sif_path="/opt/aero/containers/openfoam-esi.sif",
        host_nfs_root=tmp_path,
        remote_nfs_root=Path("/mnt/aero"),
    )
    case_dir = solver.prepare(_spec())
    fake = _FakeExecutor(stdout="  nCells: 4242")
    mesh = solver.mesh(case_dir, fake)

    assert len(fake.commands) == 1
    command = fake.commands[0]
    assert command.startswith("apptainer exec --bind ")
    assert "blockMesh" in command
    assert str(case_dir.remote_path) in command
    assert mesh.n_elements == 4242


def test_solver_prepare_writes_case_under_runs(tmp_path: Path) -> None:
    solver = OpenFOAMSolver(host_nfs_root=tmp_path, remote_nfs_root=Path("/mnt/aero"))
    case_dir = solver.prepare(_spec())
    assert case_dir.host_path.parent == tmp_path / "runs"
    assert (case_dir.host_path / "system" / "blockMeshDict").is_file()
    assert case_dir.remote_path == Path("/mnt/aero/runs") / case_dir.run_id

"""Stage 06 — SU2 adapter unit tests (pure, no cluster or SSH).

Covers the pieces that must be correct before any SU2 cluster run: the `.su2`
mesh generation, the geometric wall-normal spacing, the `.cfg` writer, the
solver's `_write_case` dispatch, and the `history.csv` / `surface_flow.csv`
parsers driven through a fake `Executor` and synthetic SU2 output files.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from aero.adapters._base import CaseDir, ResultHandle
from aero.adapters.openfoam.schemas import CaseSpec
from aero.adapters.openfoam.tmr_specs import Bump2DSpec, FlatPlateSpec
from aero.adapters.su2.cfg_writer import write_su2_cfg
from aero.adapters.su2.mesh_writer import (
    airfoil_ogrid,
    bump_grid,
    flat_plate_grid,
    geometric_spacing,
)
from aero.adapters.su2.schemas import SU2AirfoilSpec, SU2MeshFileSpec
from aero.adapters.su2.solver import SU2Solver
from aero.orchestration import ExecResult

pytestmark = pytest.mark.stage_06

_NELEM_RE = re.compile(r"^NELEM=\s*(\d+)", re.MULTILINE)
_NPOIN_RE = re.compile(r"^NPOIN=\s*(\d+)", re.MULTILINE)


# --- geometric spacing --------------------------------------------------------
def test_geometric_spacing_hits_first_cell_and_total() -> None:
    pos = geometric_spacing(40, 1.0e-6, 1.0)
    assert len(pos) == 41
    assert pos[0] == 0.0
    assert abs(pos[-1] - 1.0) < 1e-12
    assert abs((pos[1] - pos[0]) - 1.0e-6) < 1e-9  # first cell height honoured
    from itertools import pairwise

    deltas = [pos[i + 1] - pos[i] for i in range(40)]
    assert all(b >= a for a, b in pairwise(deltas))  # monotone growth


def test_geometric_spacing_rejects_degenerate_input() -> None:
    with pytest.raises(ValueError, match="n_cells"):
        geometric_spacing(0, 1e-3, 1.0)
    with pytest.raises(ValueError, match="first"):
        geometric_spacing(10, 2.0, 1.0)


# --- mesh generation ----------------------------------------------------------
def _quad_area(points: object, quad: tuple[int, int, int, int]) -> float:
    p = [points[i] for i in quad]  # type: ignore[index]
    x = [v[0] for v in p]
    y = [v[1] for v in p]
    return 0.5 * abs(sum(x[i] * y[(i + 1) % 4] - x[(i + 1) % 4] * y[i] for i in range(4)))


def test_airfoil_ogrid_is_a_closed_two_marker_mesh() -> None:
    points, quads, markers = airfoil_ogrid(
        n_surface=120, n_normal=60, radius_chords=50.0, first_cell_height=2e-6, chord=1.0
    )
    assert {m[0] for m in markers} == {"airfoil", "farfield"}
    assert len(quads) == 120 * 60  # periodic i-wrap: ni cells around
    assert all(_quad_area(points, q) > 0.0 for q in quads)  # no inverted cells


def test_airfoil_ogrid_requires_even_surface_count() -> None:
    with pytest.raises(ValueError, match="even"):
        airfoil_ogrid(
            n_surface=121, n_normal=10, radius_chords=20.0, first_cell_height=1e-5, chord=1.0
        )


def test_flat_plate_grid_splits_symmetry_and_wall_at_the_leading_edge() -> None:
    points, quads, markers = flat_plate_grid(
        plate_length=2.0,
        inlet_length=0.5,
        domain_height=1.0,
        n_streamwise=50,
        n_inlet=12,
        n_normal=40,
        first_cell_height=1e-6,
    )
    by_name = dict(markers)
    assert set(by_name) == {"symmetry", "wall", "farfield", "inlet", "outlet"}
    assert len(by_name["symmetry"]) == 12  # n_inlet line elements upstream of the LE
    assert len(by_name["wall"]) == 50  # n_streamwise line elements on the plate
    assert all(_quad_area(points, q) > 0.0 for q in quads)


def test_bump_grid_no_slip_only_on_the_bump_section() -> None:
    _, _, markers = bump_grid(
        bump_length=1.5,
        inlet_length=10.0,
        outlet_length=10.0,
        domain_height=5.0,
        bump_height=0.05,
        n_bump=60,
        n_inlet=20,
        n_outlet=20,
        n_normal=40,
        first_cell_height=2e-6,
    )
    by_name = dict(markers)
    assert len(by_name["wall"]) == 60  # only the bump section is a no-slip wall
    assert len(by_name["symmetry"]) == 40  # n_inlet + n_outlet upstream/downstream


# --- cfg writer ---------------------------------------------------------------
def test_cfg_writer_selects_roe_for_transonic_and_jst_for_subsonic(tmp_path: Path) -> None:
    transonic = tmp_path / "t.cfg"
    write_su2_cfg(
        transonic,
        mach=0.84,
        aoa_deg=3.06,
        reynolds=1.17e7,
        ref_length=1.0,
        ref_area=1.0,
        iterations=8000,
        cfl=5.0,
        turbulence_model="SA",
        n_dim=3,
        wall_markers=("WING",),
        farfield_markers=("FARFIELD",),
        symmetry_markers=("SYMMETRY",),
    )
    text = transonic.read_text()
    assert "CONV_NUM_METHOD_FLOW= ROE" in text
    assert "SOLVER= RANS" in text
    assert "MACH_NUMBER= 0.84" in text
    assert "MARKER_HEATFLUX= ( WING, 0.0 )" in text

    subsonic = tmp_path / "s.cfg"
    write_su2_cfg(
        subsonic,
        mach=0.2,
        aoa_deg=0.0,
        reynolds=5e6,
        ref_length=2.0,
        ref_area=2.0,
        iterations=3000,
        cfl=5.0,
        turbulence_model="SST",
        n_dim=2,
        wall_markers=("wall",),
        farfield_markers=("farfield",),
    )
    assert "CONV_NUM_METHOD_FLOW= JST" in subsonic.read_text()


# --- solver _write_case dispatch ---------------------------------------------
@pytest.mark.parametrize(
    "spec",
    [
        CaseSpec(name="naca0012", reynolds=6e6, mach=0.15, aoa_deg=0.0),
        SU2AirfoilSpec(name="naca0012_transonic", mach=0.7, aoa_deg=1.49, reynolds=9e6),
        FlatPlateSpec(name="flat_plate_te", reynolds=5e6, mach=0.2),
        Bump2DSpec(name="bump_2d", reynolds=3e6, mach=0.2),
    ],
)
def test_write_case_produces_valid_su2_mesh_and_cfg(spec: object, tmp_path: Path) -> None:
    solver = SU2Solver()
    solver._write_case(spec, tmp_path)  # type: ignore[arg-type]
    mesh_text = (tmp_path / "mesh.su2").read_text()
    cfg_text = (tmp_path / "case.cfg").read_text()

    n_elem = int(_NELEM_RE.search(mesh_text).group(1))  # type: ignore[union-attr]
    n_poin = int(_NPOIN_RE.search(mesh_text).group(1))  # type: ignore[union-attr]
    assert n_elem > 0 and n_poin > 0
    assert mesh_text.startswith("NDIME= 2")
    assert "SOLVER= RANS" in cfg_text
    assert "MESH_FILENAME= mesh.su2" in cfg_text


def test_write_case_rejects_an_unknown_spec(tmp_path: Path) -> None:
    class AlienSpec:
        name = "alien"

    with pytest.raises(TypeError, match="cannot write a case spec"):
        SU2Solver()._write_case(AlienSpec(), tmp_path)  # type: ignore[arg-type]


def test_mesh_file_spec_without_repo_root_fails_loud(tmp_path: Path) -> None:
    spec = SU2MeshFileSpec(
        name="onera_m6",
        mach=0.84,
        aoa_deg=3.06,
        reynolds=1.17e7,
        mesh_file="data/meshes/su2/onera_m6.su2",
        wall_markers=("WING",),
        farfield_markers=("FARFIELD",),
    )
    with pytest.raises(ValueError, match="repo_root"):
        SU2Solver()._write_case(spec, tmp_path)


# --- solver run / mesh / load / wall_distribution ----------------------------
class _FakeExecutor:
    """Records commands and returns a canned successful `ExecResult`."""

    def __init__(self) -> None:
        self.commands: list[str] = []

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
            command=command, returncode=0, stdout="", stderr="", duration_s=0.0, host="fake"
        )


def _case_dir(tmp_path: Path) -> CaseDir:
    spec = SU2AirfoilSpec(name="naca0012_transonic", mach=0.7, aoa_deg=1.49, reynolds=9e6)
    return CaseDir(
        run_id="naca0012_transonic-test",
        spec=spec,
        host_path=tmp_path,
        remote_path=Path("/mnt/aero/runs/naca0012_transonic-test"),
    )


def test_mesh_validates_the_generated_su2_file(tmp_path: Path) -> None:
    solver = SU2Solver()
    spec = SU2AirfoilSpec(name="t", mach=0.7, aoa_deg=0.0, reynolds=9e6, n_surface=40, n_normal=20)
    solver._write_case(spec, tmp_path)
    case_dir = _case_dir(tmp_path)
    mesh = solver.mesh(case_dir, _FakeExecutor())
    assert mesh.ok
    assert mesh.n_cells == 40 * 20


def test_run_builds_the_su2_cfd_command(tmp_path: Path) -> None:
    solver = SU2Solver(sif_path="/opt/aero/containers/su2-v8.sif")
    case_dir = _case_dir(tmp_path)
    fake = _FakeExecutor()
    result = solver.run(case_dir, fake)
    assert len(fake.commands) == 1
    assert fake.commands[0].startswith("apptainer exec --bind ")
    assert "SU2_CFD case.cfg" in fake.commands[0]
    assert result.returncode == 0
    assert result.output_host_path == tmp_path


def test_load_parses_su2_history_csv(tmp_path: Path) -> None:
    (tmp_path / "history.csv").write_text(
        '"Inner_Iter","rms[Rho]","CL","CD"\n'
        "0,-1.5,0.10,0.0500\n"
        "1,-3.2,0.30,0.0250\n"
        "2,-6.8,0.42,0.0193\n",
        encoding="utf-8",
    )
    result = ResultHandle(
        case_dir=_case_dir(tmp_path), returncode=0, output_host_path=tmp_path, solver_log=""
    )
    solve = SU2Solver().load(result)
    assert solve.cd == pytest.approx(0.0193)
    assert solve.cl == pytest.approx(0.42)
    assert solve.iterations_to_convergence == 3
    assert solve.final_residual == pytest.approx(-6.8)
    assert solve.history.iteration == (0, 1, 2)


def test_wall_distribution_parses_surface_flow_csv(tmp_path: Path) -> None:
    (tmp_path / "surface_flow.csv").write_text(
        '"x","Pressure_Coefficient","Skin_Friction_Coefficient_x"\n'
        "0.50,-0.20,0.0030\n"
        "0.10,0.90,0.0061\n"
        "0.90,-0.05,0.0021\n",
        encoding="utf-8",
    )
    result = ResultHandle(
        case_dir=_case_dir(tmp_path), returncode=0, output_host_path=tmp_path, solver_log=""
    )
    wd = SU2Solver().wall_distribution(result, patch="airfoil")
    assert wd.x == [0.10, 0.50, 0.90]  # sorted ascending in x
    assert wd.cp[0] == pytest.approx(0.90)
    assert wd.cf[-1] == pytest.approx(0.0021)

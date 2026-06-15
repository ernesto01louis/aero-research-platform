"""Stage 10 — OpenFOAM pressure/viscous drag decomposition.

The NACA 0012 V&V hypothesis ("the +21% excess is trailing-edge pressure drag,
not friction") was un-testable by the harness: `load()` surfaced only total Cd.
Stage 10 adds a `forces` function object whose pressure/viscous force vectors the
loader projects onto the drag direction and divides by 0.5*rho*U^2*Aref to recover
`cd_pressure` / `cd_viscous`, FAIL-LOUD-checked to reconstruct the total Cd.

These host-side tests pin the parser (both force.dat layouts), the reconstruction
gate, the controlDict wiring, and the typed SolveResult fields. End-to-end
correctness against the real ESI SIF is confirmed by the Stage-10 cluster
diagnostic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aero.adapters._base import CaseDir, ResultHandle, SolveResult
from aero.adapters.openfoam.case_writer import write_case
from aero.adapters.openfoam.schemas import CaseSpec
from aero.adapters.openfoam.solver import (
    OpenFOAMSolver,
    _maybe_force_file,
    _read_force_decomposition,
)

pytestmark = pytest.mark.stage_10


def _spec(**kw: Any) -> CaseSpec:
    base: dict[str, Any] = {"name": "naca0012", "reynolds": 6.0e6, "mach": 0.15, "aoa_deg": 0.0}
    base.update(kw)
    return CaseSpec(**base)


# --- parser: both force.dat layouts the `forces` FO has used -------------------
def test_parse_parenthesised_force_dat(tmp_path: Path) -> None:
    # ((pressure)(viscous)(porous)) ((moments...)) — pressure & viscous first.
    f = tmp_path / "force.dat"
    f.write_text(
        "# Time forces(pressure viscous porous) moment(...)\n"
        "1000 ((0.0031 0 0) (0.0067 0 0) (0 0 0)) ((0 0 0) (0 0 0) (0 0 0))\n"
    )
    cdp, cdv = _read_force_decomposition(f, drag_dir=(1.0, 0.0), q_aref=1.0)
    assert cdp == pytest.approx(0.0031)
    assert cdv == pytest.approx(0.0067)


def test_parse_flat_force_dat(tmp_path: Path) -> None:
    # Time total(3) pressure(3) viscous(3) — the flattened ESI layout.
    f = tmp_path / "force.dat"
    f.write_text(
        "# Time total_x total_y total_z pressure_x pressure_y pressure_z "
        "viscous_x viscous_y viscous_z\n"
        "1000 0.0098 0 0 0.0031 0 0 0.0067 0 0\n"
    )
    cdp, cdv = _read_force_decomposition(f, drag_dir=(1.0, 0.0), q_aref=1.0)
    assert cdp == pytest.approx(0.0031)
    assert cdv == pytest.approx(0.0067)


def test_parser_projects_onto_drag_direction(tmp_path: Path) -> None:
    # At AoA, the drag component is the force projected onto (cos a, sin a).
    f = tmp_path / "force.dat"
    f.write_text("1000 ((0.0 0.004 0) (0.005 0.0 0)) ((0 0 0) (0 0 0))\n")
    # drag_dir straight up -> picks the y-component of pressure, x of viscous.
    cdp, cdv = _read_force_decomposition(f, drag_dir=(0.0, 1.0), q_aref=1.0)
    assert cdp == pytest.approx(0.004)  # pressure y-component
    assert cdv == pytest.approx(0.0)  # viscous has no y-component


# --- locator -------------------------------------------------------------------
def test_maybe_force_file_absent_returns_none(tmp_path: Path) -> None:
    assert _maybe_force_file(tmp_path) is None


def test_maybe_force_file_finds_it(tmp_path: Path) -> None:
    d = tmp_path / "forces1" / "0"
    d.mkdir(parents=True)
    (d / "force.dat").write_text("1000 ((0 0 0)(0 0 0))\n")
    assert _maybe_force_file(tmp_path) == d / "force.dat"


# --- _drag_decomposition: reconstruction gate (FAIL-LOUD) ----------------------
def _result_with_force(tmp_path: Path, body: str) -> ResultHandle:
    post = tmp_path / "postProcessing"
    fd = post / "forces1" / "1000"
    fd.mkdir(parents=True)
    (fd / "force.dat").write_text(body)
    case_dir = CaseDir(
        run_id="r1",
        spec=_spec(),  # chord=span=1 -> q_aref = 0.5
        host_path=tmp_path,
        remote_path=Path("/case"),
    )
    return ResultHandle(case_dir=case_dir, returncode=0, output_host_path=post)


def test_decomposition_reconstructs_total(tmp_path: Path) -> None:
    # q_aref = 0.5*1*1*1 = 0.5; forces 0.0015 / 0.0033 -> Cd 0.003 / 0.0066.
    rh = _result_with_force(tmp_path, "1000 ((0.0015 0 0) (0.0033 0 0)) ((0 0 0)(0 0 0))\n")
    cdp, cdv = OpenFOAMSolver()._drag_decomposition(rh, cd_total=0.0096)
    assert cdp == pytest.approx(0.003)
    assert cdv == pytest.approx(0.0066)
    assert cdp + cdv == pytest.approx(0.0096)


def test_decomposition_fails_loud_on_layout_mismatch(tmp_path: Path) -> None:
    # If the split does not reconstruct the total Cd, the layout was mis-parsed.
    rh = _result_with_force(tmp_path, "1000 ((0.0015 0 0) (0.0033 0 0)) ((0 0 0)(0 0 0))\n")
    with pytest.raises(ValueError, match=r"unexpected force\.dat layout"):
        OpenFOAMSolver()._drag_decomposition(rh, cd_total=0.05)  # wildly inconsistent total


def test_decomposition_none_when_no_force_file(tmp_path: Path) -> None:
    post = tmp_path / "postProcessing"
    post.mkdir()
    case_dir = CaseDir(run_id="r1", spec=_spec(), host_path=tmp_path, remote_path=Path("/case"))
    rh = ResultHandle(case_dir=case_dir, returncode=0, output_host_path=post)
    assert OpenFOAMSolver()._drag_decomposition(rh, cd_total=0.0096) == (None, None)


# --- controlDict wiring + typed fields ----------------------------------------
def test_controldict_has_forces_object_with_base_patch(tmp_path: Path) -> None:
    write_case(_spec(trailing_edge_thickness=0.0025, n_te=8), tmp_path)
    cd = (tmp_path / "system" / "controlDict").read_text()
    assert "forces1" in cd
    assert "type            forces;" in cd
    assert "patches         (airfoil airfoil_te);" in cd


def test_controldict_sharp_force_patch_is_airfoil_only(tmp_path: Path) -> None:
    write_case(_spec(), tmp_path)
    cd = (tmp_path / "system" / "controlDict").read_text()
    assert "forces1" in cd
    assert "(airfoil airfoil_te)" not in cd
    assert "patches         (airfoil);" in cd


def test_solveresult_decomposition_fields_default_none() -> None:
    r = SolveResult(
        run_id="r",
        case_name="c",
        cd=0.0096,
        iterations_to_convergence=10,
        final_residual=1e-7,
        history={"kind": "convergence", "iteration": (1,), "residual": (1e-7,)},
        source="x",
    )
    assert r.cd_pressure is None and r.cd_viscous is None
    r2 = r.model_copy(update={"cd_pressure": 0.003, "cd_viscous": 0.0066})
    assert r2.cd_pressure == pytest.approx(0.003)

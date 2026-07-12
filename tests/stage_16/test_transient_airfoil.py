"""Stage 16 — transient (URANS) airfoil case: matched-condition contract with the steady case.

The URANS fallback certifies the same optimum on the same graded mesh family; its legitimacy
rests on the mesh + fields + physics being BYTE-IDENTICAL to the steady claim regime, with
only time integration differing (pimpleFoam / Euler / adjustable Courant timestep).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.openfoam.case_writer import _blockmeshdict, _fields
from aero.adapters.openfoam.transient_airfoil import (
    TransientAirfoilSpec,
    _transient_controldict,
    write_transient_airfoil_case,
)
from aero.optimize.turbulent_airfoil import ShapedTurbulentAirfoil

pytestmark = pytest.mark.stage_16


def _spec(**kw: object) -> TransientAirfoilSpec:
    base = (
        ShapedTurbulentAirfoil(max_camber=0.0727, camber_position=0.2045)
        .refined(1.0 / 1.7)
        .case_spec()
    )
    return TransientAirfoilSpec(base=base, **kw)  # type: ignore[arg-type]


def test_transient_flag_and_name_proxy() -> None:
    spec = _spec()
    assert spec.transient is True  # OpenFOAMSolver.run dispatches pimpleFoam on this
    assert spec.name == spec.base.name


def test_controldict_is_time_accurate() -> None:
    cd = _transient_controldict(_spec(end_time_convective=50.0, max_courant=2.0))
    assert "application     pimpleFoam;" in cd
    assert "adjustTimeStep  yes;" in cd
    assert "maxCo           2;" in cd
    assert "endTime         50;" in cd  # chord=1, U=1: convective times are seconds
    assert "forceCoeffs" in cd


def test_written_case_mesh_and_fields_match_steady(tmp_path: Path) -> None:
    spec = _spec()
    write_transient_airfoil_case(spec, tmp_path)
    # The matched-condition contract: mesh + initial/boundary fields byte-identical to the
    # steady writer's output for the same base spec.
    assert (tmp_path / "system" / "blockMeshDict").read_text() == _blockmeshdict(spec.base)
    steady_fields = _fields(spec.base)
    for name, text in steady_fields.items():
        assert (tmp_path / "0" / name).read_text() == text
    assert "kOmegaSST" in (tmp_path / "constant" / "turbulenceProperties").read_text()
    assert "pimpleFoam" in (tmp_path / "system" / "controlDict").read_text()
    assert "PIMPLE" in (tmp_path / "system" / "fvSolution").read_text()


def test_solver_write_case_dispatches(tmp_path: Path) -> None:
    from aero.adapters.openfoam.solver import OpenFOAMSolver

    solver = OpenFOAMSolver(host_nfs_root=tmp_path, remote_nfs_root=Path("/mnt/aero"))
    solver._write_case(_spec(), tmp_path / "case")
    assert (tmp_path / "case" / "system" / "controlDict").read_text().count("pimpleFoam") >= 1

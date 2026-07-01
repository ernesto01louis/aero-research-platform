"""Stage 11 — plunging airfoil: case rendering, dispatch, and the propulsion loader.

Host-side: pins that a PlungingAirfoilSpec renders a transient laminar moving-mesh C-grid
case (movingWallVelocity airfoil, oscillatingDisplacement, forces FO), that the adapter
dispatches it, and that _load_moving reports thrust / power / propulsive efficiency from a
synthetic converged force history. Cluster correctness is the slow test in tests/vv/.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from aero.adapters._base import CaseDir, ResultHandle
from aero.adapters.openfoam.motion import MotionSpec
from aero.adapters.openfoam.plunging_airfoil import (
    PlungingAirfoilSpec,
    heave_frequency_for_strouhal,
    write_plunging_airfoil_case,
)
from aero.adapters.openfoam.solver import OpenFOAMSolver

pytestmark = pytest.mark.stage_11

_H0 = 0.175  # heave amplitude (chords) — Heathcote-Gursul rigid foil
_STROUHAL = 0.3
_FREQ = heave_frequency_for_strouhal(strouhal=_STROUHAL, amplitude=_H0)


def _spec() -> PlungingAirfoilSpec:
    return PlungingAirfoilSpec(
        name="hg2007", reynolds=1.0e4, motion=MotionSpec(amplitude=_H0, frequency=_FREQ)
    )


def test_heave_frequency_for_strouhal() -> None:
    # St = 2 f h0 / U  ->  f = St U / (2 h0)
    assert pytest.approx(_STROUHAL / (2 * _H0)) == _FREQ


# --- case rendering + dispatch ------------------------------------------------
def test_plunging_case_renders_moving_laminar_cgrid(tmp_path: Path) -> None:
    write_plunging_airfoil_case(_spec(), tmp_path)
    cd = (tmp_path / "system" / "controlDict").read_text()
    assert "application     pimpleFoam;" in cd
    assert "patches         (airfoil);" in cd and "type            forces;" in cd
    assert (tmp_path / "constant" / "dynamicMeshDict").read_text().count("airfoil") >= 1
    pd = (tmp_path / "0" / "pointDisplacement").read_text()
    assert "oscillatingDisplacement" in pd
    u = (tmp_path / "0" / "U").read_text()
    assert "movingWallVelocity" in u
    assert (
        "simulationType  laminar;" in (tmp_path / "constant" / "turbulenceProperties").read_text()
    )
    bm = (tmp_path / "system" / "blockMeshDict").read_text()
    assert bm.count("hex (") == 8  # the eight-block C-grid (sharp TE)


def test_adapter_dispatches_plunging_spec(tmp_path: Path) -> None:
    OpenFOAMSolver()._write_case(_spec(), tmp_path)
    assert (tmp_path / "constant" / "dynamicMeshDict").exists()


# --- _load_moving propulsion branch -------------------------------------------
def _write_post(tmp_path: Path, *, thrust: float = 0.2, damping: float = 1.2) -> ResultHandle:
    omega = 2 * math.pi * _FREQ
    period = 1.0 / _FREQ
    t = np.arange(0.0, 30.0 * period, period / 40.0)
    vy = _H0 * omega * np.cos(omega * t)  # plunge velocity
    fx = np.full_like(t, -thrust)  # net thrust (F_x < 0)
    fy = -damping * vy  # transverse force opposing motion -> positive input power
    # coefficient.dat: q_aref = 0.5 (rho=U=Aref=1) -> Cd=2*Fx, Cl=2*Fy.
    post = tmp_path / "postProcessing"
    fc = post / "forceCoeffs1" / "0"
    fc.mkdir(parents=True)
    rows = [f"{ti:.8g} {2 * fxi:.8g} {2 * fyi:.8g}" for ti, fxi, fyi in zip(t, fx, fy, strict=True)]
    (fc / "coefficient.dat").write_text("# Time Cd Cl\n" + "\n".join(rows) + "\n")
    # force.dat: put the whole force in the pressure component (viscous 0).
    fd = post / "forces1" / "0"
    fd.mkdir(parents=True)
    frows = [
        f"{ti:.8g} (({fxi:.8g} {fyi:.8g} 0) (0 0 0) (0 0 0)) ((0 0 0)(0 0 0)(0 0 0))"
        for ti, fxi, fyi in zip(t, fx, fy, strict=True)
    ]
    (fd / "force.dat").write_text("\n".join(frows) + "\n")
    case_dir = CaseDir(run_id="foil1", spec=_spec(), host_path=tmp_path, remote_path=Path("/case"))
    return ResultHandle(case_dir=case_dir, returncode=0, output_host_path=post)


def test_load_moving_reports_propulsion(tmp_path: Path) -> None:
    solve = OpenFOAMSolver().load(_write_post(tmp_path))
    assert solve.scalars["cycle_converged"] == 1.0
    # thrust 0.2 / q_aref 0.5 -> C_T = 0.4.
    assert solve.scalars["thrust_coefficient"] == pytest.approx(0.4, rel=2e-2)
    assert solve.scalars["strouhal_heave"] == pytest.approx(_STROUHAL, rel=1e-3)
    # A thrust-producing, energy-consuming foil has a defined efficiency in (0, 1).
    eta = solve.scalars["propulsive_efficiency"]
    assert 0.0 < eta < 1.0

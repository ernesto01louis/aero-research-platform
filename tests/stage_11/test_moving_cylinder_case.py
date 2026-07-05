"""Stage 11 — moving (oscillating) cylinder: case rendering + the _load_moving loader.

Host-side: pins that a CylinderSpec with a MotionSpec emits the moving-mesh dicts and
the movingWallVelocity wall, and that _load_moving cycle-checks a synthetic lock-in
trace, recovers the response Strouhal, closes the force split, and FAILS LOUD on a
non-converged limit cycle. Cluster correctness is the slow test in tests/vv/.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from aero.adapters._base import CaseDir, ResultHandle
from aero.adapters.openfoam.cylinder import CylinderSpec, write_cylinder_case
from aero.adapters.openfoam.motion import MotionSpec
from aero.adapters.openfoam.solver import OpenFOAMSolver

pytestmark = pytest.mark.stage_11

_FREQ = 0.164  # forcing frequency (D = U = 1 => St = 0.164)


def _moving_spec(**kw: object) -> CylinderSpec:
    base = dict(name="osc_cyl", reynolds=100.0, inflow_angle_deg=0.0)
    base.update(kw)
    return CylinderSpec(motion=MotionSpec(amplitude=0.2, frequency=_FREQ), **base)  # type: ignore[arg-type]


# --- case rendering -----------------------------------------------------------
def test_moving_cylinder_emits_dynamic_mesh(tmp_path: Path) -> None:
    write_cylinder_case(_moving_spec(), tmp_path)
    assert (tmp_path / "constant" / "dynamicMeshDict").exists()
    pd = (tmp_path / "0" / "pointDisplacement").read_text()
    assert "oscillatingDisplacement" in pd
    u = (tmp_path / "0" / "U").read_text()
    assert "movingWallVelocity" in u and "noSlip" not in u
    fv = (tmp_path / "system" / "fvSolution").read_text()
    assert "cellDisplacement" in fv
    cd = (tmp_path / "system" / "controlDict").read_text()
    assert "forces1" in cd and "type            forces;" in cd


def test_static_cylinder_unaffected(tmp_path: Path) -> None:
    write_cylinder_case(CylinderSpec(name="static", reynolds=100.0), tmp_path)
    assert not (tmp_path / "constant" / "dynamicMeshDict").exists()
    assert "noSlip" in (tmp_path / "0" / "U").read_text()


# --- _load_moving loader ------------------------------------------------------
def _write_post(tmp_path: Path, *, converged: bool) -> ResultHandle:
    period = 1.0 / _FREQ
    t = np.arange(0.0, 45.0 * period, period / 24.0)  # ~45 cycles, 24 samples/cycle
    # converged: constant amplitude; else amplitude keeps growing (never settles).
    amp = np.full_like(t, 0.5) if converged else 0.5 * np.clip(t / t[-1] * 3.0, 0.0, None)
    cl = amp * np.sin(2 * np.pi * _FREQ * t)
    cd = np.full_like(t, 1.3)  # cd_pressure 1.0 + cd_viscous 0.3

    post = tmp_path / "postProcessing"
    fc = post / "forceCoeffs1" / "0"
    fc.mkdir(parents=True)
    rows = [f"{ti:.6g} {cdi:.6g} {cli:.6g}" for ti, cdi, cli in zip(t, cd, cl, strict=True)]
    lines = ["# Time Cd Cl", *rows]
    (fc / "coefficient.dat").write_text("\n".join(lines) + "\n")

    # forces: q_aref = 0.5 (rho=U=Aref=1); pressure drag 1.0 -> fx 0.5, viscous 0.3 -> fx 0.15.
    fd = post / "forces1" / "0"
    fd.mkdir(parents=True)
    frows = [f"{ti:.6g} ((0.5 0 0) (0.15 0 0) (0 0 0)) ((0 0 0)(0 0 0)(0 0 0))" for ti in t]
    (fd / "force.dat").write_text("\n".join(frows) + "\n")

    case_dir = CaseDir(
        run_id="mov1", spec=_moving_spec(), host_path=tmp_path, remote_path=Path("/case")
    )
    return ResultHandle(case_dir=case_dir, returncode=0, output_host_path=post)


def test_load_moving_recovers_lockin_and_split(tmp_path: Path) -> None:
    solve = OpenFOAMSolver().load(_write_post(tmp_path, converged=True))
    assert solve.scalars["cycle_converged"] == 1.0
    assert solve.scalars["strouhal"] == pytest.approx(0.164, abs=0.01)  # response = forcing
    assert solve.scalars["n_converged_cycles"] >= 4
    # cycle-mean pressure/viscous split closes to the total Cd.
    assert solve.cd_pressure == pytest.approx(1.0, abs=1e-2)
    assert solve.cd_viscous == pytest.approx(0.3, abs=1e-2)
    assert solve.cd_pressure + solve.cd_viscous == pytest.approx(1.3, abs=1e-2)


def test_load_moving_fails_loud_when_not_converged(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="periodic steady state"):
        OpenFOAMSolver().load(_write_post(tmp_path, converged=False))


def test_strictly_increasing_mask_dedupes_duplicate_timestamps() -> None:
    # OpenFOAM FO output can repeat a timestamp at adjustableRunTime write boundaries;
    # the mask must keep only strictly-increasing times so a Signal is constructible.
    import numpy as np
    from aero.adapters.openfoam.solver import _strictly_increasing_mask

    t = np.array([0.0, 0.1, 0.1, 0.2, 0.2, 0.2, 0.3])
    keep = _strictly_increasing_mask(t)
    assert list(t[keep]) == [0.0, 0.1, 0.2, 0.3]  # duplicates dropped, order preserved
    assert bool(np.all(np.diff(t[keep]) > 0.0))


def test_load_moving_survives_duplicate_timestamps(tmp_path: Path) -> None:
    # A real-data regression (the resolved foil run): duplicate FO timestamps must not
    # break the loader (previously raised 'Signal t must be strictly ascending').
    rh = _write_post(tmp_path, converged=True)
    # Duplicate every coefficient row's timestamp to mimic the write-boundary artefact.
    cf = next((rh.output_host_path / "forceCoeffs1").glob("*/coefficient.dat"))
    lines = cf.read_text().splitlines()
    dup = [lines[0]] + [ln for row in lines[1:] for ln in (row, row)]
    cf.write_text("\n".join(dup) + "\n")
    solve = OpenFOAMSolver().load(rh)  # must not raise
    assert solve.scalars["cycle_converged"] == 1.0

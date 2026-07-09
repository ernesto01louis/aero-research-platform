"""Stage 14 — flapping-wing case rendering + adapter dispatch (host-side).

Pins that a FlappingWingSpec renders a transient laminar hover case (movingWallVelocity wing,
open pressureInletOutletVelocity/totalPressure far field, NO forceCoeffs, dimensional forces FO
with CofR at the pivot, vorticity + Q FOs, the ellipse O-grid with spline edges), that BOTH
mesh-motion variants render (morph => solidBodyMotionDisplacement pointDisplacement; solid_body
=> motionSolver solidBody, no pointDisplacement), and that the adapter dispatches the spec.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from aero.adapters.openfoam.flapping_wing import FlappingWingSpec, write_flapping_wing_case
from aero.adapters.openfoam.motion import FlappingMotionSpec
from aero.adapters.openfoam.solver import OpenFOAMSolver

pytestmark = pytest.mark.stage_14


def _spec(mesh_motion: str = "overset") -> FlappingWingSpec:
    return FlappingWingSpec(
        name="wbd_test",
        reynolds=75.0,
        motion=FlappingMotionSpec(
            stroke_amplitude=1.4,
            frequency=1.0 / (math.pi * 2.8),
            pitch_amplitude_deg=45.0,
            pitch_mean_deg=90.0,
        ),
        mesh_motion=mesh_motion,  # type: ignore[arg-type]
        n_radial=40,
        n_azimuthal=24,
        end_time_cycles=2.0,
        spline_points_per_quadrant=8,
    )


def test_hover_case_renders_transient_laminar(tmp_path: Path) -> None:
    write_flapping_wing_case(_spec("morph"), tmp_path)
    cd = (tmp_path / "system" / "controlDict").read_text()
    assert "application     pimpleFoam;" in cd
    # Dimensional forces FO only — hover has no freestream so forceCoeffs is meaningless.
    assert "type            forces;" in cd
    assert "forceCoeffs" not in cd
    assert "type            vorticity;" in cd and "type            Q;" in cd
    assert "patches         (wing);" in cd
    assert (
        "simulationType  laminar;" in (tmp_path / "constant" / "turbulenceProperties").read_text()
    )


def test_hover_boundary_conditions(tmp_path: Path) -> None:
    write_flapping_wing_case(_spec(), tmp_path)
    u = (tmp_path / "0" / "U").read_text()
    assert "movingWallVelocity" in u  # no-slip in the moving frame (unbiased forces)
    assert "pressureInletOutletVelocity" in u  # open quiescent far field
    p = (tmp_path / "0" / "p").read_text()
    assert "totalPressure" in p


def test_morph_ellipse_ogrid_blockmesh(tmp_path: Path) -> None:
    write_flapping_wing_case(_spec("morph"), tmp_path)
    bm = (tmp_path / "system" / "blockMeshDict").read_text()
    assert bm.count("hex (") == 4  # 4-block O-grid (one hex per 90-deg sector, like the cylinder)
    assert "spline" in bm  # inner ellipse edges (an arc cannot represent an ellipse)
    assert "wing" in bm and "farfield" in bm


def test_forces_cofr_at_pivot(tmp_path: Path) -> None:
    write_flapping_wing_case(_spec(), tmp_path)
    cd = (tmp_path / "system" / "controlDict").read_text()
    # Pivot is the origin (the O-grid is centred there); CofR must match for correct moments.
    assert "CofR            (0 0 0);" in cd


def test_morph_variant_writes_point_displacement(tmp_path: Path) -> None:
    write_flapping_wing_case(_spec("morph"), tmp_path)
    dm = (tmp_path / "constant" / "dynamicMeshDict").read_text()
    assert "displacementLaplacian" in dm
    pd = (tmp_path / "0" / "pointDisplacement").read_text()
    assert "solidBodyMotionDisplacement" in pd
    assert "tabulated6DoFMotion" in pd
    assert (tmp_path / "constant" / "flapping_motion.dat").exists()


def test_overset_variant_writes_background_and_component(tmp_path: Path) -> None:
    write_flapping_wing_case(_spec("overset"), tmp_path)
    cd = (tmp_path / "system" / "controlDict").read_text()
    assert "application     overPimpleDyMFoam;" in cd
    # dynamicOversetFvMesh + a rigidly-moving component cellZone (multiSolidBodyMotionSolver).
    dm = (tmp_path / "constant" / "dynamicMeshDict").read_text()
    assert "dynamicOversetFvMesh" in dm and "multiSolidBodyMotionSolver" in dm
    assert "movingZone" in dm and "tabulated6DoFMotion" in dm
    # background = Cartesian box (1 hex); component = the ellipse O-grid (4 hex, spline edges).
    bg = (tmp_path / "system" / "blockMeshDict").read_text()
    assert bg.count("hex (") == 1
    comp = (tmp_path / "component" / "system" / "blockMeshDict").read_text()
    assert comp.count("hex (") == 4 and "spline" in comp and "type overset;" in comp
    # zone split + zoneID marker field + overset interpolation.
    assert (tmp_path / "system" / "topoSetDict").read_text().count("movingZone") >= 1
    assert "zoneID" in (tmp_path / "system" / "setFieldsDict").read_text()
    assert "type overset;" in (tmp_path / "0" / "zoneID").read_text()
    assert "oversetInterpolation" in (tmp_path / "system" / "fvSchemes").read_text()
    # the overset far field stays open; the wing keeps the moving-frame no-slip.
    u = (tmp_path / "0" / "U").read_text()
    assert "type overset;" in u and "movingWallVelocity" in u


def test_adapter_dispatches_flapping_spec(tmp_path: Path) -> None:
    OpenFOAMSolver()._write_case(_spec(), tmp_path)
    assert (tmp_path / "constant" / "dynamicMeshDict").exists()
    assert (tmp_path / "constant" / "flapping_motion.dat").exists()
    assert (tmp_path / "component" / "system" / "blockMeshDict").exists()

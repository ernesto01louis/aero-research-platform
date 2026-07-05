"""Stage 11 — dynamic-mesh dictionary writers + MotionSpec (host-side snapshots).

Pins the OpenFOAM grammar the moving-mesh path emits (verified against the ESI v2412
SIF tutorials): dynamicMotionSolverFvMesh + displacementLaplacian + inverseDistance,
and the oscillatingDisplacement pointDisplacement BC (field = amplitude*sin(omega*t)).
The shared transient writers must also stay byte-identical to the Stage-10 static
cylinder (no regression to the transient-cylinder GO).
"""

from __future__ import annotations

import math

import pytest
from aero.adapters.openfoam import _foam_common as fc
from aero.adapters.openfoam.cylinder import CylinderSpec, write_cylinder_case
from aero.adapters.openfoam.motion import (
    MotionSpec,
    dynamic_mesh_dict,
    point_displacement_field,
)

pytestmark = pytest.mark.stage_11


def test_motion_spec_omega() -> None:
    m = MotionSpec(amplitude=0.2, frequency=0.164)
    assert m.kind == "heave_oscillation"
    assert m.omega == pytest.approx(2 * math.pi * 0.164)


def test_dynamic_mesh_dict_grammar() -> None:
    dmd = dynamic_mesh_dict(moving_patch="cylinder")
    assert "dynamicFvMesh    dynamicMotionSolverFvMesh;" in dmd
    assert "solver           displacementLaplacian;" in dmd
    assert "diffusivity  inverseDistance (cylinder);" in dmd
    assert "motionSolverLibs (fvMotionSolvers);" in dmd


def test_point_displacement_oscillating_on_moving_wall() -> None:
    m = MotionSpec(amplitude=0.2, frequency=0.164)
    pd = point_displacement_field(
        moving_patch="cylinder",
        motion=m,
        fixed_patches=["farfield"],
        empty_patches=["front", "back"],
    )
    assert "class       pointVectorField;" in pd
    assert "type            oscillatingDisplacement;" in pd
    assert "amplitude       (0 0.2 0);" in pd  # heave in +y
    assert f"omega           {m.omega:.8g};" in pd
    # far field held fixed, 2-D planes empty.
    assert "type            fixedValue;" in pd
    assert "front { type empty; }" in pd
    assert "back { type empty; }" in pd


def test_static_cylinder_renders_shared_transient_writers(tmp_path) -> None:
    # No regression to the Stage-10 transient-cylinder GO: a static cylinder case renders
    # exactly the shared transient writers (no cellDisplacement, no motion dicts).
    write_cylinder_case(CylinderSpec(name="c", reynolds=100.0), tmp_path)
    assert (tmp_path / "system" / "fvSchemes").read_text() == fc.transient_fvschemes()
    assert (tmp_path / "system" / "fvSolution").read_text() == fc.transient_fvsolution()
    assert not (tmp_path / "constant" / "dynamicMeshDict").exists()
    assert not (tmp_path / "0" / "pointDisplacement").exists()
    assert "type noSlip;" in (tmp_path / "0" / "U").read_text()
    assert "forces1" not in (tmp_path / "system" / "controlDict").read_text()


def test_cell_displacement_solver_added_only_when_moving() -> None:
    assert "cellDisplacement" not in fc.transient_fvsolution()
    moving = fc.transient_fvsolution(cell_displacement=True)
    assert "cellDisplacement" in moving
    assert "solver          PCG;" in moving  # DIC-preconditioned PCG for the motion eqn

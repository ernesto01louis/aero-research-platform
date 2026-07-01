"""Rigid-body mesh motion for the Stage-11 moving-mesh cases.

``MotionSpec`` + the OpenFOAM dictionary writers for the **primary morphing path**
(``dynamicMotionSolverFvMesh`` + ``displacementLaplacian``, ADR-018): a deforming mesh
whose moving wall is driven by an ``oscillatingDisplacement`` ``pointDisplacement`` BC
and whose far field is fixed, with an **inverse-distance diffusivity** that keeps the
near-wall layer nearly rigid (boundary-layer preserving). The solver binary is
unchanged — ESI ``pimpleFoam`` runs a ``constant/dynamicMeshDict`` natively; only the
overset fallback would need ``overPimpleDyMFoam``.

Grammar verified against the OpenFOAM-ESI v2412 SIF tutorials and BC source: the
``oscillatingDisplacement`` field is ``amplitude * sin(omega * t)`` (so the heave is
``y(t) = amplitude * sin(omega t)``, matching
:class:`aero.postprocess.efficiency.MotionKinematics`).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aero.adapters.openfoam._foam_common import header

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)


class MotionSpec(BaseModel):
    """Prescribed rigid-body pure heave ``y(t) = amplitude * sin(2 pi frequency t)``.

    Stage 11 needs only pure heave (transverse oscillation) for the oscillating
    cylinder and the plunging airfoil; pitching / tabulated kinematics are deferred to
    Stage 13. ``amplitude`` is in the case's length units (e.g. ``0.2 * diameter`` or
    ``0.175 * chord``); ``frequency`` is in ``1/time`` (the solve is dimensionless).
    """

    model_config = _STRICT

    kind: Literal["heave_oscillation"] = "heave_oscillation"
    amplitude: float = Field(..., gt=0.0, description="Heave amplitude (length units).")
    frequency: float = Field(..., gt=0.0, description="Forcing frequency f (1/time).")

    @property
    def omega(self) -> float:
        """Angular frequency ``2 pi f`` (rad/time)."""
        return 2.0 * math.pi * self.frequency


def dynamic_mesh_dict(*, moving_patch: str, diffusivity: str = "inverseDistance") -> str:
    """``constant/dynamicMeshDict`` for the morphing path (dynamicMotionSolverFvMesh).

    The ``inverseDistance (<moving_patch>)`` diffusivity makes the Laplacian mesh-motion
    stiffness fall off with distance from the moving wall, so cells near the wall move
    nearly rigidly with it and the wall-normal spacing (y+ layer) is preserved.
    """
    return (
        header("dictionary", "dynamicMeshDict")
        + f"""
dynamicFvMesh    dynamicMotionSolverFvMesh;
motionSolverLibs (fvMotionSolvers);
solver           displacementLaplacian;
displacementLaplacianCoeffs
{{
    diffusivity  {diffusivity} ({moving_patch});
}}
"""
    )


def point_displacement_field(
    *,
    moving_patch: str,
    motion: MotionSpec,
    fixed_patches: Iterable[str],
    empty_patches: Iterable[str],
) -> str:
    """``0/pointDisplacement`` — oscillatingDisplacement on the moving wall, far field fixed.

    Heave is imposed in ``+y``; the far-field / outer patches are held fixed so the mesh
    deforms in between; ``front``/``back`` are the 2-D ``empty`` planes.
    """
    amplitude_vec = f"(0 {motion.amplitude:.8g} 0)"
    moving = f"""    {moving_patch}
    {{
        type            oscillatingDisplacement;
        amplitude       {amplitude_vec};
        omega           {motion.omega:.8g};
        value           uniform (0 0 0);
    }}"""
    fixed = "\n".join(
        f"""    {p}
    {{
        type            fixedValue;
        value           uniform (0 0 0);
    }}"""
        for p in fixed_patches
    )
    empty = "\n".join(f"    {p} {{ type empty; }}" for p in empty_patches)
    body = "\n".join(part for part in (moving, fixed, empty) if part)
    return (
        header("pointVectorField", "pointDisplacement")
        + f"""
dimensions      [0 1 0 0 0 0 0];
internalField   uniform (0 0 0);

boundaryField
{{
{body}
}}
"""
    )

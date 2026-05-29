"""Typed case specs for the SU2 v8 adapter.

SU2 is the platform's compressible/transonic solver (Stage 06). Two SU2-native
specs cover the work the OpenFOAM `CaseSpec` cannot:

* `SU2AirfoilSpec` — a 2D airfoil whose O-grid `.su2` mesh is generated from the
  analytic profile (the transonic NACA 0012 case).
* `SU2MeshFileSpec` — a case driven by a pre-supplied `.su2` mesh asset (the
  3D ONERA M6 wing, whose mesh ships with the SU2 tutorial repo under BSD).

They join into the discriminated union `SU2CaseSpec`, keyed on `kind`. The SU2
adapter *also* consumes the existing OpenFOAM TMR specs (`CaseSpec`,
`FlatPlateSpec`, `Bump2DSpec`) so the Stage-05 TMR benchmark cases run through
either solver unchanged — see `SU2Solver._write_case`.

Every model is strict (`extra='forbid'`, frozen) per `.claude/rules/
fail-loud-pydantic.md`. The lifecycle handle models are re-exported from
`aero.adapters._base` for backward-compatible imports.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from aero.adapters._base import (  # re-exported solver-neutral handles
    CaseDir as CaseDir,
)
from aero.adapters._base import (
    ConvergenceHistory as ConvergenceHistory,
)
from aero.adapters._base import (
    MeshHandle as MeshHandle,
)
from aero.adapters._base import (
    ResultHandle as ResultHandle,
)
from aero.adapters._base import (
    SolveResult as SolveResult,
)
from aero.adapters._base import (
    TimeHistory as TimeHistory,
)

# --- SU2 SIF path -------------------------------------------------------------
DEFAULT_SU2_SIF_PATH = "/opt/aero/containers/su2-v8.sif"

# SU2's RANS turbulence-model keyword. The platform names a model once; each
# adapter maps it to its solver's keyword (OpenFOAM 'kOmegaSST' -> SU2 'SST').
SU2TurbulenceModel = Literal["SA", "SST"]

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)


class SU2AirfoilSpec(BaseModel):
    """A 2D airfoil case solved by SU2 on a generated O-grid `.su2` mesh.

    Compressible RANS — the transonic regime the incompressible OpenFOAM
    `simpleFoam` adapter cannot reach. The O-grid wraps the analytic NACA 0012
    profile; `farfield_radius_chords` sets the circular far field.
    """

    model_config = _STRICT

    kind: Literal["su2_airfoil"] = "su2_airfoil"
    name: str = Field(..., min_length=1, description="Case name.")
    mach: float = Field(..., gt=0, description="Freestream Mach number.")
    aoa_deg: float = Field(..., description="Angle of attack, degrees.")
    reynolds: float = Field(..., gt=0, description="Chord Reynolds number.")
    chord: float = Field(default=1.0, gt=0, description="Airfoil chord length.")
    turbulence_model: SU2TurbulenceModel = Field(
        default="SA", description="RANS closure (Spalart-Allmaras or k-omega SST)."
    )
    iterations: int = Field(default=5000, gt=0, description="Max solver iterations.")
    cfl: float = Field(default=5.0, gt=0, description="CFL number for the implicit solve.")

    # --- generated O-grid resolution ---
    n_surface: int = Field(
        default=200, gt=7, description="Cells around the airfoil (the O-grid i-wrap)."
    )
    n_normal: int = Field(default=120, gt=3, description="Cells wall-normal to the far field.")
    farfield_radius_chords: float = Field(
        default=50.0, gt=1.0, description="Circular far-field radius, in chords."
    )
    first_cell_height: float = Field(
        default=2.0e-6, gt=0, description="Wall-normal first-cell height, in chords."
    )


class SU2MeshFileSpec(BaseModel):
    """An SU2 case driven by a pre-supplied `.su2` mesh asset.

    For geometries the platform does not generate analytically — notably the
    3D ONERA M6 wing, whose `.su2` mesh ships with the SU2 tutorial repository
    (BSD-licensed, mirrored under `data/meshes/su2/`).
    """

    model_config = _STRICT

    kind: Literal["su2_mesh_file"] = "su2_mesh_file"
    name: str = Field(..., min_length=1, description="Case name.")
    mach: float = Field(..., gt=0, description="Freestream Mach number.")
    aoa_deg: float = Field(..., description="Angle of attack, degrees.")
    reynolds: float = Field(..., gt=0, description="Reynolds number based on `ref_length`.")
    mesh_file: str = Field(
        ...,
        min_length=1,
        description="Repo-relative path to the `.su2` mesh asset (DVC-tracked).",
    )
    n_dim: Literal[2, 3] = Field(default=3, description="Mesh dimensionality.")
    ref_area: float = Field(default=1.0, gt=0, description="Aerodynamic reference area.")
    ref_length: float = Field(default=1.0, gt=0, description="Aerodynamic reference length.")
    wall_markers: tuple[str, ...] = Field(
        ..., description="Mesh marker names of the no-slip wall(s)."
    )
    farfield_markers: tuple[str, ...] = Field(
        ..., description="Mesh marker names of the far-field boundary."
    )
    symmetry_markers: tuple[str, ...] = Field(
        default=(), description="Mesh marker names of any symmetry plane."
    )
    turbulence_model: SU2TurbulenceModel = Field(default="SA", description="RANS closure.")
    iterations: int = Field(default=8000, gt=0, description="Max solver iterations.")
    cfl: float = Field(default=5.0, gt=0, description="CFL number for the implicit solve.")


SU2CaseSpec = Annotated[SU2AirfoilSpec | SU2MeshFileSpec, Field(discriminator="kind")]
"""Discriminated union of the SU2-native case specs, keyed on `kind`."""

__all__ = [
    "DEFAULT_SU2_SIF_PATH",
    "CaseDir",
    "ConvergenceHistory",
    "MeshHandle",
    "ResultHandle",
    "SU2AirfoilSpec",
    "SU2CaseSpec",
    "SU2MeshFileSpec",
    "SU2TurbulenceModel",
    "SolveResult",
    "TimeHistory",
]

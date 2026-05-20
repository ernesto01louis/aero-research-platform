"""Typed contracts for the OpenFOAM adapter.

`CaseSpec` is the OpenFOAM-specific airfoil case spec — intentionally
mesh-coupled (its C-grid fields are meaningless for another solver). The
lifecycle handle models (`CaseDir`, `MeshHandle`, `ResultHandle`) and the
shared NFS-path constants were promoted to `aero.adapters._base` in Stage 06
when SU2 forced the multi-solver abstraction (ADR-006); they are re-exported
here so existing `aero.adapters.openfoam.schemas` imports keep working.

Every model is strict (`extra='forbid'`, frozen) per `.claude/rules/
fail-loud-pydantic.md` — unknown keys are drift and must fail at validation
time, not silently corrupt a provenance record.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Lifecycle handles + platform paths now live in the solver-agnostic base.
from aero.adapters._base import (
    CASE_BIND_TARGET,
    DEFAULT_HOST_NFS_ROOT,
    DEFAULT_REMOTE_NFS_ROOT,
    RUNS_SUBDIR,
    CaseDir,
    MeshHandle,
    ResultHandle,
)

# --- OpenFOAM SIF path --------------------------------------------------------
# The shared NFS-path constants come from `_base`; the SIF path is per-solver.
DEFAULT_SIF_PATH = "/opt/aero/containers/openfoam-esi.sif"

# Shared strict config — see .claude/rules/fail-loud-pydantic.md.
_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

__all__ = [
    "CASE_BIND_TARGET",
    "DEFAULT_HOST_NFS_ROOT",
    "DEFAULT_REMOTE_NFS_ROOT",
    "DEFAULT_SIF_PATH",
    "RUNS_SUBDIR",
    "CaseDir",
    "CaseSpec",
    "MeshHandle",
    "ResultHandle",
]


class CaseSpec(BaseModel):
    """A NACA-class external-aerodynamics case for incompressible `simpleFoam`.

    Physical state is dimensionless: the solve fixes Reynolds number and a
    unit freestream speed, deriving kinematic viscosity from them. `mach` is
    recorded as part of the reference condition but does not enter an
    incompressible solve.
    """

    model_config = _STRICT

    name: str = Field(..., min_length=1, description="Case name, e.g. 'naca0012'.")
    reynolds: float = Field(..., gt=0, description="Chord Reynolds number.")
    mach: float = Field(..., gt=0, description="Reference Mach number (recorded only).")
    aoa_deg: float = Field(..., description="Angle of attack, degrees.")
    chord: float = Field(default=1.0, gt=0, description="Chord length.")
    span: float = Field(default=1.0, gt=0, description="Spanwise extent (one cell, 2D).")
    end_time: int = Field(default=1500, gt=0, description="Max SIMPLE iterations.")
    turbulence_model: Literal["kOmegaSST"] = Field(
        default="kOmegaSST", description="RAS turbulence closure."
    )

    # --- mesh resolution (2D multi-block C-grid) ---
    # The Stage-05 C-grid replaces the Stage-03 four-block O-grid: a rectangular
    # far field at `farfield_extent_chords`, an explicit wake cut downstream of
    # the trailing edge, and the airfoil surface split at mid-chord. See ADR-005.
    farfield_extent_chords: float = Field(
        default=100.0, gt=1.0, description="Rectangular far-field half-extent, in chords."
    )
    n_surface: int = Field(
        default=120, gt=3, description="Cells along each airfoil surface half (LE-mid, mid-TE)."
    )
    n_normal: int = Field(default=120, gt=3, description="Cells wall-normal to the far field.")
    n_front: int = Field(
        default=48, gt=3, description="Streamwise cells in the front block (inlet to LE)."
    )
    n_wake: int = Field(
        default=72, gt=3, description="Streamwise cells in the wake block (TE to outlet)."
    )
    first_cell_height: float = Field(
        default=2.0e-6, gt=0, description="Wall-normal first-cell height, in chords."
    )
    turbulence_intensity: float = Field(
        default=0.001, gt=0, description="Freestream turbulence intensity (fraction)."
    )

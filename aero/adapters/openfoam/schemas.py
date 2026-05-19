"""Typed contracts for the OpenFOAM walking-skeleton adapter.

Every model is strict (`extra='forbid'`, frozen) per `.claude/rules/
fail-loud-pydantic.md` — unknown keys are drift and must fail at validation
time, not silently corrupt a provenance record.

These types are intentionally OpenFOAM-specific. The multi-solver abstraction
is Stage 06's job, when SU2 forces it (ADR-003).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# --- platform paths -----------------------------------------------------------
# The aero NFS dataset is mounted at different points on the CLI host and
# inside the aero LXC; a case written on one side is read on the other.
DEFAULT_HOST_NFS_ROOT = Path("/mnt/aero-nfs")
DEFAULT_REMOTE_NFS_ROOT = Path("/mnt/aero")
RUNS_SUBDIR = "runs"
DEFAULT_SIF_PATH = "/opt/aero/containers/openfoam-esi.sif"
CASE_BIND_TARGET = "/case"  # where the case dir is bind-mounted inside the SIF

# Shared strict config — see fail-loud-pydantic.md.
_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)


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


class CaseDir(BaseModel):
    """A prepared OpenFOAM case directory on the shared NFS dataset.

    The same bytes are visible at `host_path` (where the aero process wrote
    them) and at `remote_path` (where the SIF reads them inside the LXC).
    """

    model_config = _STRICT

    run_id: str = Field(..., min_length=1, description="Unique run identifier.")
    spec: CaseSpec = Field(..., description="The spec this case was built from.")
    host_path: Path = Field(..., description="Case path as seen by the aero process.")
    remote_path: Path = Field(..., description="Case path as seen inside the LXC/SIF.")


class MeshHandle(BaseModel):
    """Outcome of the `blockMesh` step."""

    model_config = _STRICT

    case_dir: CaseDir = Field(..., description="The meshed case.")
    ok: bool = Field(..., description="True iff blockMesh succeeded and polyMesh exists.")
    n_cells: int | None = Field(default=None, description="Cell count, if reported.")


class ResultHandle(BaseModel):
    """Outcome of the `simpleFoam` solve."""

    model_config = _STRICT

    case_dir: CaseDir = Field(..., description="The solved case.")
    returncode: int = Field(..., description="simpleFoam exit code; 0 is success.")
    post_processing_host_path: Path = Field(
        ..., description="postProcessing/ directory, host-side."
    )
    solver_log: str = Field(default="", description="Captured simpleFoam output.")

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

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Lifecycle handles + platform paths now live in the solver-agnostic base.
from aero.adapters._base import (
    CASE_BIND_TARGET,
    DEFAULT_HOST_NFS_ROOT,
    DEFAULT_REMOTE_NFS_ROOT,
    RUNS_SUBDIR,
    CaseDir,
    ConvergenceHistory,
    MeshHandle,
    ResultHandle,
    SolveResult,
    TimeHistory,
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
    "ConvergenceHistory",
    "MeshHandle",
    "ResultHandle",
    "SolveResult",
    "TimeHistory",
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
    turbulence_model: Literal["kOmegaSST", "laminar"] = Field(
        default="kOmegaSST",
        description="RAS closure ('kOmegaSST'), or 'laminar' (no model) for the "
        "forward-regime low-Re airfoil — sub-transition, no k/omega/nut transport.",
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
    # --- trailing-edge closure (Stage 09 blunt-TE C-grid; ADR-012) ---
    trailing_edge_thickness: float = Field(
        default=0.0,
        ge=0.0,
        description="Blunt-TE full base thickness in chords; 0 = sharp/closed TE (default). "
        ">0 selects the standard NACA 0012 open-TE geometry, splitting the singular TE "
        "vertex into a finite base to address the +21% pressure-drag error. The blunt TE "
        "is the FIXED standard open-TE section (full thickness ~0.00252c); this field is "
        "validated against that geometry (a value inconsistent with it fails loud — it is "
        "not a free knob), so the recorded value is faithful to the mesh in config_hash.",
    )
    n_te: int = Field(
        default=0,
        ge=0,
        description="Cells across the blunt-TE base; required >=1 when trailing_edge_thickness>0.",
    )

    @model_validator(mode="after")
    def _blunt_te_needs_base_cells(self) -> CaseSpec:
        if self.trailing_edge_thickness > 0.0 and self.n_te < 1:
            raise ValueError(
                "trailing_edge_thickness>0 (blunt TE) requires n_te>=1 (cells across the base)"
            )
        return self

    @model_validator(mode="after")
    def _blunt_te_matches_geometry(self) -> CaseSpec:
        # FAIL-LOUD (Hard Rule 2): the blunt TE meshes the FIXED standard
        # open-TE geometry, whose full base thickness is set by the airfoil
        # quartic, not by this field. Require the recorded value to match it so
        # a misleading value (e.g. 0.01) cannot be silently ignored — the
        # config_hash must describe the geometry that was actually meshed.
        if self.trailing_edge_thickness > 0.0:
            from aero.adapters.openfoam.geometry import OPEN_TE_FULL_THICKNESS

            rel = (
                abs(self.trailing_edge_thickness - OPEN_TE_FULL_THICKNESS) / OPEN_TE_FULL_THICKNESS
            )
            if rel > 0.05:
                raise ValueError(
                    f"trailing_edge_thickness={self.trailing_edge_thickness} is inconsistent "
                    f"with the standard NACA 0012 open-TE full base thickness "
                    f"{OPEN_TE_FULL_THICKNESS:.5f}c that the blunt-TE mesh actually uses. "
                    f"Set it to ~{OPEN_TE_FULL_THICKNESS:.4f} (the open-TE thickness) or 0 "
                    f"for a sharp TE; this field records the geometry, it does not size it."
                )
        return self

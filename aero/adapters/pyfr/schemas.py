"""Typed case specs for the PyFR adapter (Stage 07).

Two PyFR-native specs cover the cases Stage 07 ships:

* `PyFRTaylorGreenSpec` — the triply-periodic Taylor-Green vortex (the
  canonical high-order accuracy benchmark; reference dissipation rate at
  Re = 1600 from Brachet et al. 1983, JFM 130).
* `PyFRMeshFileSpec` — a case driven by a pre-supplied gmsh `.msh` mesh
  asset (the periodic-hill LES case; mesh DVC-tracked).

They join into the discriminated union `PyFRSpec`, keyed on `kind`.

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

# --- PyFR SIF path -----------------------------------------------------------
DEFAULT_PYFR_SIF_PATH = "/opt/aero/containers/pyfr.sif"

# PyFR backend selector. `cuda` runs on NVIDIA H100/A100/L40S via PyCUDA;
# `hip` on AMD MI-series; `openmp` is the CPU fallback (Stage 07 verifies the
# H100 path; the others are stubs Stage 13's multi-cloud router will exercise).
PyFRBackend = Literal["cuda", "hip", "openmp"]

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)


class PyFRTaylorGreenSpec(BaseModel):
    """Spec for the Taylor-Green vortex case at Re = 1600 (canonical high-order DNS).

    The triply-periodic cube `[-pi, pi]^3` with the analytic Taylor-Green
    initial condition. `pyfr` integrates Navier-Stokes; the kinetic-energy
    dissipation rate trace is compared against Brachet et al. 1983 DNS in
    the V&V harness.

    `n_elements_per_dir` x `n_elements_per_dir` x `n_elements_per_dir` hex
    elements, polynomial order `p`; total DOF = N³ x (p+1)³. Re=1600 with
    p=3, N=32 is the canonical workshop benchmark (`HiFiLES`/PyFR/NekRS all
    agree to within a few percent on the dissipation peak).
    """

    model_config = _STRICT

    kind: Literal["pyfr_taylor_green"] = "pyfr_taylor_green"
    name: str = Field(..., min_length=1, description="Case name.")
    reynolds: float = Field(
        default=1600.0, gt=0, description="Reynolds number (Brachet canonical: 1600)."
    )
    mach: float = Field(
        default=0.08,
        gt=0,
        lt=0.3,
        description="Reference Mach (quasi-incompressible regime).",
    )
    n_elements_per_dir: int = Field(
        default=32, ge=8, le=128, description="Hex elements per spatial direction."
    )
    polynomial_order: int = Field(
        default=3, ge=2, le=6, description="FR polynomial order p (DOF = N^3 * (p+1)^3)."
    )
    t_end: float = Field(
        default=20.0,
        gt=0,
        description="End time in convective time units (Brachet integrates to t=20).",
    )
    dt: float = Field(
        default=1e-3, gt=0, description="Time step (CFL-limited for the chosen order)."
    )
    monitor_dt: float = Field(
        default=0.1,
        gt=0,
        description="Cadence the kinetic-energy / dissipation monitor writes (s of sim time).",
    )
    backend: PyFRBackend = Field(default="cuda", description="PyFR compute backend.")


class PyFRMeshFileSpec(BaseModel):
    """A PyFR case driven by a pre-supplied gmsh `.msh` mesh + Jinja `.ini` template."""

    model_config = _STRICT

    kind: Literal["pyfr_mesh_file"] = "pyfr_mesh_file"
    name: str = Field(..., min_length=1, description="Case name.")
    mesh_file: str = Field(
        ...,
        min_length=1,
        description="Repo-relative path to the `.msh` mesh asset (DVC-tracked).",
    )
    cfg_template: str = Field(
        ...,
        min_length=1,
        description="Repo-relative path to the PyFR `solver.ini` (or `.ini.j2`) template.",
    )
    polynomial_order: int = Field(..., ge=1, le=6, description="FR polynomial order.")
    t_end: float = Field(..., gt=0, description="End time (solver-relative units).")
    dt: float = Field(..., gt=0, description="Time step.")
    monitor_dt: float = Field(..., gt=0, description="Monitor cadence.")
    backend: PyFRBackend = Field(default="cuda", description="PyFR compute backend.")


PyFRSpec = Annotated[PyFRTaylorGreenSpec | PyFRMeshFileSpec, Field(discriminator="kind")]
"""Discriminated union of the PyFR-native case specs, keyed on `kind`."""

__all__ = [
    "DEFAULT_PYFR_SIF_PATH",
    "CaseDir",
    "ConvergenceHistory",
    "MeshHandle",
    "PyFRBackend",
    "PyFRMeshFileSpec",
    "PyFRSpec",
    "PyFRTaylorGreenSpec",
    "ResultHandle",
    "SolveResult",
    "TimeHistory",
]

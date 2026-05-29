"""Typed case specs for the NekRS adapter (Stage 07).

Two NekRS-native specs cover the cases Stage 07 ships:

* `NekRSTaylorGreenSpec` — the triply-periodic Taylor-Green vortex, NekRS
  flavour (the box-mesh + `.par` + `.udf` are generated host-side from
  string templates).
* `NekRSCaseDirSpec` — a case whose `.re2` + `.par` + `.udf` (+ optional
  `.oudf`) live in a repo-tracked directory copied verbatim into the run
  directory (the periodic-hill LES case; assets DVC-tracked).

They join into the discriminated union `NekRSSpec`, keyed on `kind`.

Every model is strict (`extra='forbid'`, frozen).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from aero.adapters._base import (
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

# --- NekRS SIF path ----------------------------------------------------------
DEFAULT_NEKRS_SIF_PATH = "/opt/aero/containers/nekrs.sif"

# OCCA backend selector — NekRS's runtime-chosen device backend.
NekRSBackend = Literal["CUDA", "HIP", "CPU"]

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)


class NekRSTaylorGreenSpec(BaseModel):
    """Spec for the Taylor-Green vortex case in NekRS, generated from templates.

    The triply-periodic cube `[-pi, pi]^3`. NekRS uses spectral elements:
    `n_elements_per_dir ** 3` total elements at polynomial order `N`
    (typically N=7 for canonical TG). DOF = N_elem * (N+1)^3.

    The host-side `_write_case` step emits a `.box` file (driven through
    `genbox` in the SIF at `mesh()`), a `.par` file (NekRS runtime
    parameters), and a `.udf` file (the analytic TG initial condition).
    """

    model_config = _STRICT

    kind: Literal["nekrs_taylor_green"] = "nekrs_taylor_green"
    name: str = Field(..., min_length=1)
    case_name: str = Field(
        default="taylorGreen",
        min_length=1,
        description="Nek5000 case-name stem; `<case_name>.{box,par,udf,re2}`.",
    )
    reynolds: float = Field(default=1600.0, gt=0)
    n_elements_per_dir: int = Field(default=8, ge=4, le=32)
    polynomial_order: int = Field(default=7, ge=3, le=11)
    t_end: float = Field(default=20.0, gt=0)
    dt: float = Field(default=5e-4, gt=0)
    monitor_dt: float = Field(default=0.1, gt=0)
    backend: NekRSBackend = Field(default="CUDA")


class NekRSCaseDirSpec(BaseModel):
    """A NekRS case whose `.re2` + `.par` + `.udf` ship in a repo-tracked dir."""

    model_config = _STRICT

    kind: Literal["nekrs_case_dir"] = "nekrs_case_dir"
    name: str = Field(..., min_length=1)
    case_name: str = Field(
        ...,
        min_length=1,
        description="Nek5000 case-name stem (must match the file basenames).",
    )
    case_dir: str = Field(
        ...,
        min_length=1,
        description="Repo-relative path to the case-asset directory (DVC-tracked).",
    )
    polynomial_order: int = Field(..., ge=3, le=11)
    t_end: float = Field(..., gt=0)
    dt: float = Field(..., gt=0)
    monitor_dt: float = Field(..., gt=0)
    backend: NekRSBackend = Field(default="CUDA")


NekRSSpec = Annotated[NekRSTaylorGreenSpec | NekRSCaseDirSpec, Field(discriminator="kind")]

__all__ = [
    "DEFAULT_NEKRS_SIF_PATH",
    "CaseDir",
    "ConvergenceHistory",
    "MeshHandle",
    "NekRSBackend",
    "NekRSCaseDirSpec",
    "NekRSSpec",
    "NekRSTaylorGreenSpec",
    "ResultHandle",
    "SolveResult",
    "TimeHistory",
]

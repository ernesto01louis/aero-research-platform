"""Typed case specs for the JAX-Fluids adapter (Stage 08).

Two JAX-Fluids-native specs cover the Stage-08 smoke surface:

* :class:`JaxFluidsShockTubeSpec` — Sod's 1D shock tube, the canonical
  compressible-CFD verification problem with an analytic Riemann-problem
  reference solution.
* :class:`JaxFluidsMeshFileSpec` — a case driven by a pre-supplied JSON
  ``case_setup.json`` + ``numerical_setup.json`` pair (JAX-Fluids' native
  driver format).

They join into the discriminated union ``JaxFluidsSpec``, keyed on ``kind``.

Strict pydantic, frozen. ``.claude/rules/fail-loud-pydantic.md``.
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

DEFAULT_JAX_FLUIDS_SIF_PATH = "/opt/aero/containers/jax-fluids.sif"

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)


class JaxFluidsShockTubeSpec(BaseModel):
    """Sod's 1D shock-tube case (canonical JAX-Fluids smoke).

    Initial discriminator at ``x = 0.5`` of the unit domain:

    * Left:  ``(rho, u, p) = (1.0, 0.0, 1.0)``
    * Right: ``(rho, u, p) = (0.125, 0.0, 0.1)``

    At ``t_end = 0.2`` the shock has propagated ~0.18 units to the right;
    Stage-08 V&V asserts the shock position is within ±2% of the analytic
    Riemann-problem solution. Mesh and time-step defaults match JAX-Fluids'
    tutorial settings.
    """

    model_config = _STRICT

    kind: Literal["jaxf_shock_tube"] = "jaxf_shock_tube"
    name: str = Field(..., min_length=1)
    n_cells: int = Field(default=256, ge=64, le=2048, description="Cells in x.")
    cfl: float = Field(default=0.5, gt=0.0, lt=1.0, description="CFL number.")
    t_end: float = Field(default=0.2, gt=0.0, description="Simulation end time.")
    monitor_dt: float = Field(
        default=0.01, gt=0.0, description="Cadence of the shock-position monitor."
    )


class JaxFluidsMeshFileSpec(BaseModel):
    """A JAX-Fluids case driven by pre-supplied native JSON case files."""

    model_config = _STRICT

    kind: Literal["jaxf_mesh_file"] = "jaxf_mesh_file"
    name: str = Field(..., min_length=1)
    case_setup_path: str = Field(
        ..., min_length=1, description="Repo-relative path to `case_setup.json`."
    )
    numerical_setup_path: str = Field(
        ..., min_length=1, description="Repo-relative path to `numerical_setup.json`."
    )


JaxFluidsSpec = Annotated[
    JaxFluidsShockTubeSpec | JaxFluidsMeshFileSpec,
    Field(discriminator="kind"),
]
"""Discriminated union of JAX-Fluids case specs, keyed on ``kind``."""


class JaxGradientResult(BaseModel):
    """Return of :meth:`JaxFluidsSolver.differentiable_run`.

    Carries the primal :class:`SolveResult` (the same shape as the
    SIF-executor path produces) plus a typed mapping from gradient-target
    parameter name to gradient pytree leaves (as ``tuple[float, ...]`` for
    Pydantic-strict round-tripping). Stage 13's adjoint optimisation layer
    consumes this directly; cost-cap and four-fold provenance do NOT apply
    because the in-process path bypasses the executor by design (ADR-008
    §D3).
    """

    model_config = _STRICT

    primal: SolveResult = Field(
        ..., description="The forward solve result, same shape as `run` + `load` produce."
    )
    jax_grad_target: str = Field(
        ..., min_length=1, description="The parameter name the gradient is taken with respect to."
    )
    gradients: dict[str, tuple[float, ...]] = Field(
        ...,
        description="Pytree-leaf-flattened gradient values, keyed on leaf path "
        "(e.g. 'initial_condition.rho_left').",
    )


__all__ = [
    "DEFAULT_JAX_FLUIDS_SIF_PATH",
    "CaseDir",
    "ConvergenceHistory",
    "JaxFluidsMeshFileSpec",
    "JaxFluidsShockTubeSpec",
    "JaxFluidsSpec",
    "JaxGradientResult",
    "MeshHandle",
    "ResultHandle",
    "SolveResult",
    "TimeHistory",
]

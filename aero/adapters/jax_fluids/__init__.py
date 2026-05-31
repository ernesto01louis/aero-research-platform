"""JAX-Fluids adapter — Stage 08's fifth and first-differentiable solver (ADR-008).

JAX-Fluids 2.x (upstream tag ``JAX-Fluids-v0.2.1``, MIT-licensed) is a
pure-JAX compressible CFD code. This adapter provides:

* :class:`JaxFluidsSolver` — fifth concrete :class:`Solver` implementing
  the standard imperative lifecycle via the SIF executor (parity with
  OpenFOAM / SU2 / PyFR / NekRS — same four-fold provenance, same
  cost-cap path).
* :meth:`JaxFluidsSolver.differentiable_run` — additive in-process method
  exposing JAX gradients; bypasses the executor and cost-cap by design
  (ADR-008 §D3). The ``Solver`` ABC is NOT amended.

The two case specs (:class:`JaxFluidsShockTubeSpec`,
:class:`JaxFluidsMeshFileSpec`) join in the discriminated
:data:`JaxFluidsSpec` union, keyed on ``kind``.
"""

from aero.adapters.jax_fluids.schemas import (
    DEFAULT_JAX_FLUIDS_SIF_PATH,
    JaxFluidsMeshFileSpec,
    JaxFluidsShockTubeSpec,
    JaxFluidsSpec,
    JaxGradientResult,
)
from aero.adapters.jax_fluids.solver import JaxFluidsSolver

__all__ = [
    "DEFAULT_JAX_FLUIDS_SIF_PATH",
    "JaxFluidsMeshFileSpec",
    "JaxFluidsShockTubeSpec",
    "JaxFluidsSolver",
    "JaxFluidsSpec",
    "JaxGradientResult",
]

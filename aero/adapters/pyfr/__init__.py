"""PyFR adapter — Stage 07's third concrete solver (ADR-007).

PyFR is a high-order flux-reconstruction GPU-resident scale-resolving CFD
code (BSD-3); the platform's first time-accurate solver. This adapter
provides the third concrete `Solver` implementation, satisfies the typed
`SolverProtocol`, and emits `TimeHistory` (not `ConvergenceHistory`) from
`load()` — the Stage-07 protocol promotion.
"""

from aero.adapters.pyfr.schemas import (
    DEFAULT_PYFR_SIF_PATH,
    PyFRBackend,
    PyFRMeshFileSpec,
    PyFRSpec,
    PyFRTaylorGreenSpec,
)
from aero.adapters.pyfr.solver import PyFRSolver

__all__ = [
    "DEFAULT_PYFR_SIF_PATH",
    "PyFRBackend",
    "PyFRMeshFileSpec",
    "PyFRSolver",
    "PyFRSpec",
    "PyFRTaylorGreenSpec",
]

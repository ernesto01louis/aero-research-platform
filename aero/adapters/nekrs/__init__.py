"""NekRS adapter — Stage 07's fourth concrete solver (ADR-007).

NekRS is a GPU-resident spectral-element CFD code (BSD-3) derived from
Nek5000, with OCCA + libParanumal backends for cross-vendor GPU portability.
This adapter is the fourth concrete `Solver` implementation; like PyFR it
emits `TimeHistory` (not `ConvergenceHistory`) from `load()` — the
Stage-07 protocol promotion.
"""

from aero.adapters.nekrs.schemas import (
    DEFAULT_NEKRS_SIF_PATH,
    NekRSBackend,
    NekRSCaseDirSpec,
    NekRSSpec,
    NekRSTaylorGreenSpec,
)
from aero.adapters.nekrs.solver import NekRSSolver

__all__ = [
    "DEFAULT_NEKRS_SIF_PATH",
    "NekRSBackend",
    "NekRSCaseDirSpec",
    "NekRSSolver",
    "NekRSSpec",
    "NekRSTaylorGreenSpec",
]

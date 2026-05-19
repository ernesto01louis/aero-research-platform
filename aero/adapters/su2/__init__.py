"""SU2 v8 adapter — the platform's compressible/transonic CFD solver (Stage 06).

The second concrete `Solver` (after OpenFOAM-ESI); the one that forced the
shared abstraction in `aero.adapters._base` (ADR-006).
"""

from __future__ import annotations

from aero.adapters.su2.schemas import SU2AirfoilSpec, SU2CaseSpec, SU2MeshFileSpec
from aero.adapters.su2.solver import SU2Solver

__all__ = ["SU2AirfoilSpec", "SU2CaseSpec", "SU2MeshFileSpec", "SU2Solver"]

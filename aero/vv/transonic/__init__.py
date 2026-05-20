"""The transonic V&V cases — Stage 06's compressible-aerodynamics benchmark set.

Two canonical cases: the 2D transonic NACA 0012 (M=0.7, AoA=1.49 deg, Cd vs
AGARD-AR-138 / Schmitt-Charpin) and the 3D ONERA M6 wing (M=0.84, AoA=3.06 deg,
Cp vs Schmitt-Charpin / ONERA TR-1). Both are SU2-primary; an OpenFOAM
`rhoCentralFoam` cross-check is best-effort and not gating.

`TRANSONIC_CASES` is the registry the `aero vv` CLI and the
`vv-transonic.yml` nightly workflow iterate.
"""

from __future__ import annotations

from aero.vv._base import BenchmarkCase
from aero.vv.transonic.naca0012_transonic import NACA0012Transonic
from aero.vv.transonic.onera_m6 import OneraM6

TRANSONIC_CASES: dict[str, BenchmarkCase] = {
    NACA0012Transonic.name: NACA0012Transonic(),
    OneraM6.name: OneraM6(),
}

__all__ = ["TRANSONIC_CASES", "NACA0012Transonic", "OneraM6"]

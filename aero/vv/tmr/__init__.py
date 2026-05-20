"""The NASA TMR verification cases — the Stage 05 V&V benchmark set.

`TMR_CASES` is the registry the `aero vv` CLI and the V&V test suite iterate.
Each value is a `BenchmarkCase` (it satisfies the protocol in `aero.vv._base`).
"""

from __future__ import annotations

from aero.vv._base import BenchmarkCase
from aero.vv.tmr.bump_2d import Bump2D
from aero.vv.tmr.flat_plate import FlatPlateTE
from aero.vv.tmr.naca0012 import NACA0012Verification

TMR_CASES: dict[str, BenchmarkCase] = {
    FlatPlateTE.name: FlatPlateTE(),
    Bump2D.name: Bump2D(),
    NACA0012Verification.name: NACA0012Verification(),
}

__all__ = ["TMR_CASES", "Bump2D", "FlatPlateTE", "NACA0012Verification"]

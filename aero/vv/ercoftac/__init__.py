"""ERCOFTAC transition V&V cases — the transitional regime the flapping optimizer needs.

The forward-regime cases (`aero.vv.forward_regime`) anchor the laminar + turbulent-shedding
regimes; the ERCOFTAC T3 series anchors the **transitional** regime (bypass transition under
free-stream turbulence) that the Langtry-Menter gamma-Re_theta model (`kOmegaSSTLM`, Stage 13)
targets. This registry is the transition-onset half of the Stage-13 GO gate.

* `T3AFlatPlate` — ERCOFTAC T3A flat plate (3% FSTI); Cf(x) + transition-onset Re_x vs the
  Savill/ERCOFTAC data (a faithful port of the ESI v2412 T3A tutorial).

`ERCOFTAC_CASES` is the registry the `aero vv` CLI iterates.
"""

from __future__ import annotations

from aero.vv._base import BenchmarkCase
from aero.vv.ercoftac.t3a_flat_plate import T3AFlatPlate

ERCOFTAC_CASES: dict[str, BenchmarkCase] = {
    T3AFlatPlate.name: T3AFlatPlate(),
}

__all__ = ["ERCOFTAC_CASES", "T3AFlatPlate"]

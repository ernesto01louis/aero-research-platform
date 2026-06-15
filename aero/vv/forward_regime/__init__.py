"""Forward-regime canonical V&V cases — the low-Re laminar/transitional regime
the flapping-wing optimizer actually operates in (Re ~ 10^2-10^4).

The NASA TMR cases (`aero.vv.tmr`) are fully-turbulent RANS table-stakes; these
cases anchor the solver in the *mission's own* flow regime, against canonical
analytical / experimental references (the flapping-validation-ladder rule's
"forward-regime credibility" tier). Added Stage 10.

* `BlasiusFlatPlate` — laminar zero-pressure-gradient flat plate vs the exact
  Blasius skin-friction law (Cf = 0.664/sqrt(Re_x)).

(The laminar/transitional airfoil and the low-Re cylinder vortex-shedding
Strouhal case follow; the cylinder needs the transient solve path, which is
Stage-11 unsteady machinery.)

`FORWARD_REGIME_CASES` is the registry the `aero vv` CLI iterates.
"""

from __future__ import annotations

from aero.vv._base import BenchmarkCase
from aero.vv.forward_regime.blasius_flat_plate import BlasiusFlatPlate

FORWARD_REGIME_CASES: dict[str, BenchmarkCase] = {
    BlasiusFlatPlate.name: BlasiusFlatPlate(),
}

__all__ = ["FORWARD_REGIME_CASES", "BlasiusFlatPlate"]

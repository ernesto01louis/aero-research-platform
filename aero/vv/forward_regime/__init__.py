"""Forward-regime canonical V&V cases — the low-Re laminar/transitional regime
the flapping-wing optimizer actually operates in (Re ~ 10^2-10^4).

The NASA TMR cases (`aero.vv.tmr`) are fully-turbulent RANS table-stakes; these
cases anchor the solver in the *mission's own* flow regime, against canonical
analytical / experimental references (the flapping-validation-ladder rule's
"forward-regime credibility" tier). Added Stage 10.

* `BlasiusFlatPlate` — laminar zero-pressure-gradient flat plate vs the exact
  Blasius skin-friction law (Cf = 0.664/sqrt(Re_x)).
* `LaminarAirfoil` — laminar NACA 0012 at Re=1000, AoA=0 (low-Re Cd vs Kurtuluş
  2015 + the Cl=0 symmetry sanity).

(The low-Re cylinder vortex-shedding Strouhal case follows; it needs the
transient solve path — Stage-11 unsteady machinery.)

`FORWARD_REGIME_CASES` is the registry the `aero vv` CLI iterates.
"""

from __future__ import annotations

from aero.vv._base import BenchmarkCase
from aero.vv.forward_regime.blasius_flat_plate import BlasiusFlatPlate
from aero.vv.forward_regime.laminar_airfoil import LaminarAirfoil

FORWARD_REGIME_CASES: dict[str, BenchmarkCase] = {
    BlasiusFlatPlate.name: BlasiusFlatPlate(),
    LaminarAirfoil.name: LaminarAirfoil(),
}

__all__ = ["FORWARD_REGIME_CASES", "BlasiusFlatPlate", "LaminarAirfoil"]

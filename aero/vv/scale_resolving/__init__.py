"""The scale-resolving V&V cases — Stage 07's canonical high-order benchmark set.

Two cases:

* `TaylorGreenVortex` (Re = 1600) — the workshop-canonical dissipation-rate
  trace; reference is Brachet et al. (1983, JFM 130), the original DNS.
* `PeriodicHillLES` — the canonical separated-flow LES benchmark; reference
  is Breuer & Rapp/Manhart wall-shear data. Full pointwise mean-velocity
  profile comparison is a Stage-12 follow-up; Stage 07 ships only the
  bulk re-attachment-length scalar (and fails loud when the wall sampler
  output is missing).

Both cases are solver-agnostic: pass either a PyFR or NekRS-flavoured spec
into the constructor (the `solver_kind` arg dispatches).

`SCALE_RESOLVING_CASES` is the registry the `aero vv` CLI and the
`vv-scale-resolving.yml` nightly workflow iterate.
"""

from __future__ import annotations

from aero.vv._base import BenchmarkCase
from aero.vv.scale_resolving.periodic_hill import PeriodicHillLES
from aero.vv.scale_resolving.taylor_green import TaylorGreenVortex

SCALE_RESOLVING_CASES: dict[str, BenchmarkCase] = {
    "taylor_green_p3_32": TaylorGreenVortex(solver_kind="pyfr"),
    "periodic_hill_2d": PeriodicHillLES(solver_kind="pyfr"),
}

__all__ = [
    "SCALE_RESOLVING_CASES",
    "PeriodicHillLES",
    "TaylorGreenVortex",
]

"""Unsteady / moving-body V&V cases — the flapping-ladder "unsteady machinery" tier.

Moving-mesh cases that validate the Stage-11 unsteady capability against experiment/DNS:

* `OscillatingCylinderLockin` — forced transversely-oscillating cylinder (Re=100); the
  wake locks to the forcing frequency (Placzek 2009; Koopmann 1967). The Stage-11 primary
  GO — cheap, first-principles, exact laminar regime.
* `PlungingAirfoilHG2007` — rigid plunging NACA-0012 (Re=1e4, h0/c=0.175); time-averaged
  thrust vs Heathcote & Gursul (2007) (VALIDATE-AGAINST-EXPERIMENT). Laminar 2-D, honest
  15% band.

Stage 13 will add the pitching / dynamic-stall cases (McCroskey) to this registry.
`UNSTEADY_CASES` is the registry the `aero vv` CLI iterates.
"""

from __future__ import annotations

from aero.vv._base import BenchmarkCase
from aero.vv.unsteady.oscillating_cylinder import OscillatingCylinderLockin
from aero.vv.unsteady.plunging_airfoil import PlungingAirfoilHG2007

UNSTEADY_CASES: dict[str, BenchmarkCase] = {
    OscillatingCylinderLockin.name: OscillatingCylinderLockin(),
    PlungingAirfoilHG2007.name: PlungingAirfoilHG2007(),
}

__all__ = ["UNSTEADY_CASES", "OscillatingCylinderLockin", "PlungingAirfoilHG2007"]

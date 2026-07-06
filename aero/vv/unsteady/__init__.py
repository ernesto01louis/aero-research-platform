"""Unsteady / moving-body V&V cases — the flapping-ladder "unsteady machinery" tier.

Moving-mesh cases that validate the Stage-11 unsteady capability against experiment/DNS:

* `OscillatingCylinderLockin` — forced transversely-oscillating cylinder (Re=100); the
  wake locks to the forcing frequency (Placzek 2009; Koopmann 1967). The Stage-11 primary
  GO — cheap, first-principles, exact laminar regime.
* `PlungingAirfoilHG2007` — rigid plunging NACA-0012 (Re=1e4, h0/c=0.175); time-averaged
  thrust vs Heathcote & Gursul (2007) (VALIDATE-AGAINST-EXPERIMENT). The Stage-11 base is
  laminar 2-D at St=0.4 (a documented over-prediction CONCERN). Stage 13 adds **re-anchored**
  variants at pre-bifurcation St 0.2 / 0.3 (in-range measured points), each in a laminar and
  a `kOmegaSSTLM` (gamma-Re_theta transition) flavour — the paired comparison that resolves
  the over-prediction.

`UNSTEADY_CASES` is the registry the `aero vv` CLI iterates.
"""

from __future__ import annotations

from aero.vv._base import BenchmarkCase
from aero.vv.unsteady.oscillating_cylinder import OscillatingCylinderLockin
from aero.vv.unsteady.plunging_airfoil import PlungingAirfoilHG2007


def _plunging_variants() -> dict[str, BenchmarkCase]:
    """The Stage-11 base (St=0.4 laminar) + the Stage-13 re-anchored St 0.2/0.3 x {laminar,
    kOmegaSSTLM} paired-comparison variants, keyed by their registry name."""
    cases: list[PlungingAirfoilHG2007] = [PlungingAirfoilHG2007()]  # base St=0.4 laminar
    for st in (0.2, 0.3):
        for tm in ("laminar", "kOmegaSSTLM"):
            cases.append(PlungingAirfoilHG2007(strouhal=st, turbulence_model=tm))
    return {c.name: c for c in cases}


UNSTEADY_CASES: dict[str, BenchmarkCase] = {
    OscillatingCylinderLockin.name: OscillatingCylinderLockin(),
    **_plunging_variants(),
}

__all__ = ["UNSTEADY_CASES", "OscillatingCylinderLockin", "PlungingAirfoilHG2007"]

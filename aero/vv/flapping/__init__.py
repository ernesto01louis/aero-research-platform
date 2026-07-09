"""Flapping-wing V&V cases — the Stage-14 flagship forward-capability tier.

Rigid 2-D flapping wing in hover validated against Wang, Birch & Dickinson (2004):

* `FlappingWingWBD2004` — a thin elliptic wing performing the WBD idealised stroke
  (A0/c = 2.8, Re = 75). The **symmetrical** rotation timing is the GO-gated case
  (stroke-averaged mean lift vs the robotic-wing experiment); the **advanced** and
  **delayed** timings are diagnostic variants (the Dickinson 1999 rotation-timing
  lift-enhancement signature; delayed is a documented 2-D failure).

`FLAPPING_CASES` is the registry the `aero vv` CLI iterates. This is the last validated
forward problem before the Stage-15 CFD-in-the-loop optimizer.
"""

from __future__ import annotations

from typing import get_args

from aero.vv._base import BenchmarkCase
from aero.vv.flapping.wbd2004 import FlappingWingWBD2004, RotationTiming


def _flapping_variants() -> dict[str, BenchmarkCase]:
    """The gated symmetrical case + the advanced/delayed diagnostic rotation-timing variants."""
    cases = [FlappingWingWBD2004(rotation_timing=t) for t in get_args(RotationTiming)]
    return {c.name: c for c in cases}


FLAPPING_CASES: dict[str, BenchmarkCase] = _flapping_variants()

__all__ = ["FLAPPING_CASES", "FlappingWingWBD2004"]

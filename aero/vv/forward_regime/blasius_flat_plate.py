"""Laminar flat plate vs the Blasius solution — forward-regime Cf verification.

A zero-pressure-gradient *laminar* flat plate (Re_L = 1e5, below transition):
the exact reference is Blasius' similarity solution, whose local skin friction
is ``Cf(x) = 0.664 / sqrt(Re_x)`` with ``Re_x = U x / nu = Re_L * x / L``
(H. Blasius 1908; Schlichting, *Boundary-Layer Theory*). Unlike the turbulent
TMR plate this needs no turbulence model — it is the cleanest possible check
that the laminar momentum/viscous discretisation reproduces a known boundary
layer, in the low-Re regime the flapping optimizer operates in.

The metric is the local Cf distribution along the plate, compared pointwise
(5%) against the analytical law tabulated in
``data/references/forward_regime/blasius_flat_plate/cf.csv``.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from aero.adapters.openfoam.tmr_specs import FlatPlateSpec
from aero.vv._base import (
    BenchmarkError,
    MetricSpec,
    ReferenceData,
    Series,
    SolverLike,
    load_series_csv,
    scaled_count,
)


def blasius_cf(x: float, *, reynolds: float, plate_length: float) -> float:
    """Blasius local skin-friction coefficient at chordwise station `x`.

    ``Cf = 0.664 / sqrt(Re_x)``, ``Re_x = reynolds * x / plate_length`` (the
    case Reynolds number is based on the plate length). Defined for x > 0; the
    law is singular at the leading edge.
    """
    if x <= 0.0:
        raise ValueError(f"Blasius Cf is singular at/upstream of the LE (x={x})")
    re_x = reynolds * x / plate_length
    return 0.664 / math.sqrt(re_x)


class BlasiusFlatPlate:
    """Laminar flat plate (Re_L = 1e5, M = 0.1) — Blasius Cf verification."""

    name = "blasius_flat_plate"
    description = "Laminar flat plate vs the Blasius Cf law (forward-regime, low-Re)."
    sweep_metric = "cf_mid"

    def __init__(self, spec: FlatPlateSpec | None = None) -> None:
        self._spec = spec or FlatPlateSpec(
            name=self.name,
            reynolds=1.0e5,  # whole plate laminar (Re_x < 5e5 transition everywhere)
            mach=0.1,
            turbulence_model="laminar",
            # A coarser near-wall first cell than the turbulent plate: y+ is
            # irrelevant for a laminar solve, and the laminar BL is far thicker.
            first_cell_height=1.0e-5,
        )

    def case_spec(self) -> FlatPlateSpec:
        return self._spec

    def reference(self, repo_root: Path) -> ReferenceData:
        cf = load_series_csv(
            repo_root / "data" / "references" / "forward_regime" / "blasius_flat_plate" / "cf.csv",
            x_col="x",
            y_col="cf",
        )
        return ReferenceData(
            case_name=self.name,
            source="Blasius laminar flat-plate solution, Cf = 0.664/sqrt(Re_x) "
            "(Schlichting, Boundary-Layer Theory)",
            series={"cf": cf},
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        return (MetricSpec(name="cf", kind="pointwise", tolerance=0.05, comparison="relative"),)

    # Drop the leading-edge region: Blasius Cf ~ x^-0.5 is singular at x=0 and a
    # spline through the near-LE rise overshoots the reference there.
    _LE_WINDOW = 0.1

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        wd = solver.wall_distribution(result, patch="wall")
        pts = [
            (x, cf)
            for x, cf in zip(wd.x, wd.cf, strict=True)
            if self._LE_WINDOW <= x <= self._spec.plate_length
        ]
        if len(pts) < 2:
            raise BenchmarkError("blasius flat plate: fewer than two wall samples on the plate")
        cf = Series(x=tuple(p[0] for p in pts), y=tuple(p[1] for p in pts))
        x_mid = 0.5 * self._spec.plate_length
        cf_mid = min(zip(cf.x, cf.y, strict=True), key=lambda p: abs(p[0] - x_mid))[1]
        return {"cf": cf, "cf_mid": cf_mid}

    def refined(self, ratio: float) -> BlasiusFlatPlate:
        s = self._spec
        return BlasiusFlatPlate(
            s.model_copy(
                update={
                    "n_streamwise": scaled_count(s.n_streamwise, ratio),
                    "n_normal": scaled_count(s.n_normal, ratio),
                    "n_inlet": scaled_count(s.n_inlet, ratio),
                }
            )
        )

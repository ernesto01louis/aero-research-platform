"""The NASA TMR turbulent flat-plate V&V case.

A zero-pressure-gradient turbulent flat plate — the canonical check that a
turbulence model reproduces the known flat-plate skin-friction law. The metric
is the local Cf distribution along the plate, compared pointwise (5%, ADR-005)
against the White correlation reference (`data/references/tmr/flat_plate/`).
"""

from __future__ import annotations

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


class FlatPlateTE:
    """TMR turbulent flat plate (Re_L = 5e6, M = 0.2) — Cf verification."""

    name = "flat_plate_te"
    description = "NASA TMR turbulent flat plate — skin-friction (Cf) verification."
    sweep_metric = "cf_mid"

    def __init__(self, spec: FlatPlateSpec | None = None) -> None:
        self._spec = spec or FlatPlateSpec(name=self.name, reynolds=5.0e6, mach=0.2)

    def case_spec(self) -> FlatPlateSpec:
        return self._spec

    def reference(self, repo_root: Path) -> ReferenceData:
        cf = load_series_csv(
            repo_root / "data" / "references" / "tmr" / "flat_plate" / "cf.csv",
            x_col="x",
            y_col="cf",
        )
        return ReferenceData(
            case_name=self.name,
            source="White turbulent flat-plate Cf correlation (Viscous Fluid Flow, 3rd ed.)",
            series={"cf": cf},
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        return (MetricSpec(name="cf", kind="pointwise", tolerance=0.05, comparison="relative"),)

    # Compare from here back: Cf ~ x^-0.2 is singular at the leading edge, and
    # a spline through the near-LE spike overshoots the reference at x ~ 0.05.
    _LE_WINDOW = 0.1

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        wd = solver.wall_distribution(result, patch="wall")
        # Keep the developed plate, dropping the leading-edge singularity.
        pts = [
            (x, cf)
            for x, cf in zip(wd.x, wd.cf, strict=True)
            if self._LE_WINDOW <= x <= self._spec.plate_length
        ]
        if len(pts) < 2:
            raise BenchmarkError("flat plate: fewer than two wall samples on the plate")
        cf = Series(x=tuple(p[0] for p in pts), y=tuple(p[1] for p in pts))
        # `cf_mid` (Cf nearest mid-plate) is the scalar the GCI mesh sweep tracks.
        x_mid = 0.5 * self._spec.plate_length
        cf_mid = min(zip(cf.x, cf.y, strict=True), key=lambda p: abs(p[0] - x_mid))[1]
        return {"cf": cf, "cf_mid": cf_mid}

    def refined(self, ratio: float) -> FlatPlateTE:
        s = self._spec
        return FlatPlateTE(
            s.model_copy(
                update={
                    "n_streamwise": scaled_count(s.n_streamwise, ratio),
                    "n_normal": scaled_count(s.n_normal, ratio),
                    "n_inlet": scaled_count(s.n_inlet, ratio),
                }
            )
        )

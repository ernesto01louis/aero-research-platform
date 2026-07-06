"""ERCOFTAC T3A transitional flat plate — kOmegaSSTLM transition-onset verification.

The canonical verification case for the Langtry-Menter gamma-Re_theta transition model
(`kOmegaSSTLM`, added Stage 13): a flat plate under ~3% free-stream turbulence intensity
transitions at Re_x ~ 1.4e5. The measured Cf(x) falls (laminar), reaches a minimum at
transition onset, then rises (turbulent). This is the transition-onset half of the Stage-13
GO gate (Hard Rule 15 — VALIDATE-AGAINST-EXPERIMENT).

The case is a faithful port of the ESI v2412 T3A tutorial (see
`aero.adapters.openfoam.t3a`). It is **dimensional** (U_inf = 5.4 m/s), so `evaluate()` passes
`u_inf` to the wall-distribution parser and maps the sampled physical x to x-from-leading-edge.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from aero.adapters.openfoam.t3a import T3A_PLATE_LENGTH, T3A_PLATE_X0, T3ASpec
from aero.vv._base import (
    BenchmarkError,
    MetricSpec,
    ReferenceData,
    Series,
    SolverLike,
    load_series_csv,
)

# LE guard for the onset search: the leading-edge / contoured-nose junction can carry a
# spurious near-wall Cf that would mislocate the minimum; the measured transition is well
# downstream (~0.4 m). The reference table also starts at x = 0.045 m from the LE.
_ONSET_X_GUARD = 0.04


def _onset_rex(x: tuple[float, ...], cf: tuple[float, ...], *, u_inf: float, nu: float) -> float:
    """Transition-onset Re_x = U_inf * x_min / nu at the Cf minimum, x measured from the LE.

    The minimum is searched over ``x >= _ONSET_X_GUARD`` so a near-LE junction artifact
    cannot masquerade as transition onset.
    """
    xa = np.asarray(x)
    cfa = np.asarray(cf)
    mask = xa >= _ONSET_X_GUARD
    if mask.sum() < 2:
        raise BenchmarkError(f"T3A: fewer than two Cf samples beyond x={_ONSET_X_GUARD} m")
    x_win = xa[mask]
    x_min = float(x_win[int(np.argmin(cfa[mask]))])
    return u_inf * x_min / nu


class T3AFlatPlate:
    """ERCOFTAC T3A flat plate (3% FSTI) — kOmegaSSTLM transition-onset verification."""

    name = "t3a_flat_plate_transition"
    description = (
        "ERCOFTAC T3A transitional flat plate (3% FSTI) — Cf(x) + transition-onset Re_x "
        "vs the Savill/ERCOFTAC data; verifies the kOmegaSSTLM (gamma-Re_theta) model."
    )
    sweep_metric = "transition_onset_rex"

    def __init__(self, spec: T3ASpec | None = None) -> None:
        self._spec = spec or T3ASpec(name=self.name)

    def case_spec(self) -> T3ASpec:
        return self._spec

    def reference(self, repo_root: Path) -> ReferenceData:
        cf = load_series_csv(
            repo_root / "data" / "references" / "ercoftac" / "t3a" / "cf.csv",
            x_col="x",
            y_col="cf",
        )
        # Derive the reference onset Re_x with the SAME Cf-minimum definition used on the
        # solve, so the comparison is apples-to-apples.
        onset = _onset_rex(cf.x, cf.y, u_inf=self._spec.u_inf, nu=self._spec.nu)
        return ReferenceData(
            case_name=self.name,
            source="ERCOFTAC T3A (3% FSTI); Savill 1993/1996, via the OpenFOAM-ESI v2412 "
            "tutorial exptData/T3A.dat",
            series={"cf": cf},
            scalars={"transition_onset_rex": onset},
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        return (
            # Primary GO metric: transition-onset location (scale-invariant Cf minimum).
            MetricSpec(
                name="transition_onset_rex",
                kind="scalar",
                tolerance=0.20,
                comparison="relative",
            ),
            # Secondary: the full Cf(x) curve, max error normalised by peak Cf.
            MetricSpec(name="cf", kind="pointwise", tolerance=0.25, comparison="normalized"),
        )

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        # Flat-plate Cf comes from the wall sampler, not forceCoeffs; the dimensional T3A
        # case supplies its u_inf so Cf is normalised by 0.5*U_inf^2 (not the platform's 1.0).
        wd = solver.wall_distribution(result, patch="plate", u_inf=self._spec.u_inf)
        pts = [
            (x - T3A_PLATE_X0, cf)
            for x, cf in zip(wd.x, wd.cf, strict=True)
            if 0.0 < (x - T3A_PLATE_X0) <= T3A_PLATE_LENGTH  # 0 < x-from-LE <= plate length
        ]
        pts.sort(key=lambda p: p[0])
        if len(pts) < 2:
            raise BenchmarkError("T3A: fewer than two wall samples on the plate")
        cf = Series(x=tuple(p[0] for p in pts), y=tuple(p[1] for p in pts))
        onset = _onset_rex(cf.x, cf.y, u_inf=self._spec.u_inf, nu=self._spec.nu)
        return {"cf": cf, "transition_onset_rex": onset}

    def refined(self, ratio: float) -> T3AFlatPlate:
        # ratio >= 1 coarsens (mesh_factor scales down); the tutorial mesh is the base (1.0).
        return T3AFlatPlate(
            self._spec.model_copy(update={"mesh_factor": self._spec.mesh_factor / ratio})
        )

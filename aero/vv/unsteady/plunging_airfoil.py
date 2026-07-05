"""Rigid plunging airfoil — time-averaged thrust vs Heathcote-Gursul (2007).

A rigid NACA-0012 heaving sinusoidally (amplitude h0/c = 0.175) in a freestream produces
net thrust above a critical Strouhal number St = 2 f h0 / U. Heathcote & Gursul (2007,
AIAA J 45(5):1066-1079) measured the rigid ("steel") foil mean thrust coefficient vs St at
Re = 1e4-3e4 (they report the thrust to be Reynolds-independent over that range). This is
the Stage-11 experiment-anchored ladder rung (VALIDATE-AGAINST-EXPERIMENT).

**Regime + tolerance (honest band, operator-approved).** Kept laminar / 2-D (transition is
Stage 13): 2-D laminar Navier-Stokes reproduces the plunging-foil wake + thrust well at
Re ~ 1e4 (the thrust is dominated by the leading-edge vortex + circulatory/added-mass
pressure forces, not the boundary-layer state). The 15 % tolerance honestly reflects (i)
the 2-D-laminar vs 3-D-transitional-experiment model gap, and (ii) the NACA-0012-vs-teardrop
geometry substitution. **Fallback if the band is missed** (never relax to pass): validate
the *trend* (C_T monotone in St; net-thrust threshold near St ~ 0.13) and/or a published
CFD-reproduction value, documented as a CONCERN. Reference C_T values are digitized from the
HG rigid-foil curve (see reference.md for the digitization provenance + u95_input).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aero.adapters.openfoam.motion import MotionSpec
from aero.adapters.openfoam.plunging_airfoil import (
    PlungingAirfoilSpec,
    heave_frequency_for_strouhal,
)
from aero.vv._base import (
    MetricSpec,
    ReferenceData,
    Series,
    SolverLike,
    load_scalar_csv,
    scaled_count,
)

_STROUHAL = 0.4  # anchor St = 2 f h0 / U (strong net thrust; the rigid-foil transition St)
_AMP_RATIO = 0.175  # h0 / c (Heathcote-Gursul)


class PlungingAirfoilHG2007:
    """Rigid plunging NACA-0012 (Re=1e4, h0/c=0.175, St=0.4) — thrust vs Heathcote-Gursul."""

    name = "plunging_airfoil_hg2007"
    description = (
        "Rigid plunging NACA-0012 (Re=1e4, h0/c=0.175, St=0.4) — time-averaged thrust "
        "coefficient vs Heathcote & Gursul 2007 rigid-foil experiment (laminar 2-D)."
    )
    sweep_metric = "thrust_coefficient"

    def __init__(self, spec: PlungingAirfoilSpec | None = None) -> None:
        if spec is None:
            f = heave_frequency_for_strouhal(strouhal=_STROUHAL, amplitude=_AMP_RATIO)
            spec = PlungingAirfoilSpec(
                name=self.name,
                reynolds=1.0e4,
                motion=MotionSpec(amplitude=_AMP_RATIO, frequency=f),
                # Cost-tuned for a tractable single-grid campaign. The thrust is
                # pressure/vortex-dominated (added-mass + circulatory + LEV), NOT
                # skin-friction, so a first cell of 2e-3 c (~4-5 cells in the Re=1e4 laminar
                # BL, delta ~ c/sqrt(Re) ~ 0.01c) is adequate; the limit cycle is reached in
                # ~10-15 plunge periods so ~18 periods (end_time 18) leaves a converged tail;
                # maxCo=1.0 (2 outer + 2 inner PIMPLE correctors) keeps the moving-wall
                # timestep affordable. A finer-grid / GCI confirmation is a Stage-12 follow-up.
                first_cell_height=2.0e-3,
                n_surface=90,
                n_normal=70,
                n_front=48,
                n_wake=72,
                end_time_convective=18.0,
                write_interval_convective=0.02,
                max_courant=1.0,
            )
        self._spec = spec

    def case_spec(self) -> PlungingAirfoilSpec:
        return self._spec

    def reference(self, repo_root: Path) -> ReferenceData:
        ct = load_scalar_csv(
            repo_root
            / "data"
            / "references"
            / "unsteady"
            / "plunging_airfoil_hg2007"
            / "thrust.csv",
            key_col="strouhal",
            key=_STROUHAL,
            value_col="thrust_coefficient",
        )
        return ReferenceData(
            case_name=self.name,
            source="Heathcote & Gursul 2007 (AIAA J 45(5):1066-1079), rigid-foil mean thrust",
            scalars={"thrust_coefficient": ct},
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        return (
            MetricSpec(
                name="thrust_coefficient", kind="scalar", tolerance=0.15, comparison="relative"
            ),
        )

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        # solver.load() raises unless the limit cycle converged; C_T is the mean over the
        # converged cycles (aero.postprocess.efficiency.propulsive_metrics).
        solve = solver.load(result)
        ct = solve.scalars.get("thrust_coefficient")
        if ct is None:
            raise ValueError(
                f"{self.name}: SolveResult.scalars['thrust_coefficient'] missing — the moving "
                "loader did not compute propulsion (is this a plunging-airfoil spec?)."
            )
        return {"thrust_coefficient": ct}

    def refined(self, ratio: float) -> PlungingAirfoilHG2007:
        s = self._spec
        return PlungingAirfoilHG2007(
            s.model_copy(
                update={
                    "n_surface": scaled_count(s.n_surface, ratio),
                    "n_normal": scaled_count(s.n_normal, ratio),
                    "n_front": scaled_count(s.n_front, ratio),
                    "n_wake": scaled_count(s.n_wake, ratio),
                }
            )
        )

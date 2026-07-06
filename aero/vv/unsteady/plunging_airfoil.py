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
_U_INF = 1.0  # dimensionless freestream (Re fixes nu)


def _variant_name(strouhal: float, turbulence_model: str) -> str:
    """Registry key for a plunging variant. St=0.4 laminar keeps the historical base name."""
    if strouhal == _STROUHAL and turbulence_model == "laminar":
        return "plunging_airfoil_hg2007"
    suffix = f"_st{round(strouhal * 10):02d}"
    if turbulence_model == "kOmegaSSTLM":
        suffix += "_lm"
    return "plunging_airfoil_hg2007" + suffix


def _spec_strouhal(spec: PlungingAirfoilSpec) -> float:
    """Recover St = 2 f h0 / U from a spec's motion (h0 = amplitude, U = _U_INF)."""
    return 2.0 * spec.motion.frequency * spec.motion.amplitude / _U_INF


def _end_time_for_strouhal(strouhal: float) -> float:
    """~22 plunge periods (T = 2 h0 / St convective times) — settle + a >=8-cycle tail."""
    return 8.0 / strouhal


class PlungingAirfoilHG2007:
    """Rigid plunging NACA-0012 (Re=1e4, h0/c=0.175, St=0.4) — thrust vs Heathcote-Gursul."""

    name = "plunging_airfoil_hg2007"
    description = (
        "Rigid plunging NACA-0012 (Re=1e4, h0/c=0.175, St=0.4) — time-averaged thrust "
        "coefficient vs Heathcote & Gursul 2007 rigid-foil experiment (laminar 2-D)."
    )
    sweep_metric = "thrust_coefficient"

    def __init__(
        self,
        spec: PlungingAirfoilSpec | None = None,
        *,
        strouhal: float = _STROUHAL,
        turbulence_model: str = "laminar",
    ) -> None:
        self._strouhal = strouhal if spec is None else _spec_strouhal(spec)
        tm = turbulence_model if spec is None else spec.turbulence_model
        # Base case (St=0.4, laminar) keeps the historical name; re-anchored / transition
        # variants get a distinct registry key so their run dirs + provenance don't collide.
        self.name = _variant_name(self._strouhal, tm)
        if spec is None:
            f = heave_frequency_for_strouhal(strouhal=strouhal, amplitude=_AMP_RATIO)
            transition = turbulence_model == "kOmegaSSTLM"
            spec = PlungingAirfoilSpec(
                name=self.name,
                reynolds=1.0e4,
                motion=MotionSpec(amplitude=_AMP_RATIO, frequency=f),
                turbulence_model=turbulence_model,  # type: ignore[arg-type]
                # Laminar AND kOmegaSSTLM share the Stage-11-proven moving-mesh resolution
                # (2e-3 first cell, n=90/70, maxCo=1.0) — a clean paired comparison where ONLY
                # the turbulence model differs. This costs the transition probe some wall
                # resolution (y+ ~ 1.4 vs the textbook y+<1), which the kOmegaSSTLM wall
                # functions (omegaWallFunction/nutkWallFunction) tolerate; documented as a
                # qualitative probe, not a wall-resolved transition study. (A finer 5e-4 mesh
                # both diverged the moving-mesh startup — SIGFPE — and drove dt ~ 1e-4, making
                # the run serially infeasible at ~60 h.)
                first_cell_height=2.0e-3,
                n_surface=90,
                n_normal=70,
                n_front=48,
                n_wake=72,
                # ~22 plunge periods: settle (~8-10) + a converged tail >= 8 cycles for
                # batch-means. Period T = 2*h0/St convective times, so scale end time with 1/St.
                end_time_convective=_end_time_for_strouhal(strouhal),
                write_interval_convective=0.02,
                max_courant=1.0,
                turbulence_intensity=0.01 if transition else 0.001,
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
            key=self._strouhal,
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
        out: dict[str, float | Series] = {"thrust_coefficient": ct}
        # Also expose the cycle-mean Cd (a smooth Richardson target, C_T = -mean Cd) so the
        # space+time GCI (scripts/stage13_gci.py) can extrapolate it via measure_scalar. Not a
        # gated metric — metrics() only contracts thrust_coefficient.
        if solve.cd is not None:
            out["cd"] = solve.cd
        return out

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

    def refined_dt(self, ratio: float) -> PlungingAirfoilHG2007:
        """A copy with a COARSER timestep (``max_courant`` scaled by ``ratio``), fixed mesh.

        The temporal analogue of :meth:`refined` for a combined space+time GCI (the Stage-12
        cylinder pattern): the moving-mesh timestep is Courant-driven (``max_courant``), which
        :meth:`refined` cannot touch. ``ratio == 1.0`` is the base (finest) dt; ``ratio > 1``
        coarsens (a larger Courant cap -> larger dt).
        """
        if ratio <= 0.0:
            raise ValueError(f"refined_dt ratio must be > 0, got {ratio}")
        s = self._spec
        return PlungingAirfoilHG2007(s.model_copy(update={"max_courant": s.max_courant * ratio}))

"""The optimizer's turbulent forward airfoil case: a shaped NACA-4 at higher Re (Stage-15).

The steady *laminar* Re=1000 case (`airfoil_case.py`) cannot certify a thesis-grade optimization
delta: the high-L/D cambered designs the optimizer finds have a mildly unsteady wake that steady
`simpleFoam` cannot converge at resolvable grids (the delta's grid-convergence breaks down where the
improvement lives — established over the Stage-15 V&V campaigns + two adversarial audits). A
**fully-turbulent RANS closure (k-omega SST)** supplies eddy viscosity that damps the wake, so
loaded/cambered airfoils converge STEADILY and the L/D grid-converges on a y+<1 mesh. This is the
standard airfoil shape-optimization regime, where a steady GCI-on-the-delta is physically valid.

Same shape parametrization (NACA-4 camber, y-only on fixed cosine x-stations → matched topology) and
the same `BenchmarkCase` duck-type as `ShapedLaminarAirfoil`, so it runs through the existing
`BenchmarkRunner`, `CFDObjective`, and 3-grid V&V driver unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aero.adapters.openfoam.schemas import CaseSpec
from aero.vv._base import MetricSpec, ReferenceData, Series, SolverLike, scaled_count

_BASE_AOA = (
    4.0  # lift to improve; attached turbulent BL is steady well past the laminar shedding onset
)
_BASE_RE = (
    5.0e5  # moderate, fully turbulent, tractable: wall-function mesh solves in minutes + stable
)
_BASE_END_TIME = (
    3000  # a well-conditioned wall-function mesh converges fast (no near-wall stiffness)
)

# Tractable wall-function mesh (Stage-15 turbulent-optimizer rescue). A y+<1 mesh at high Re has an
# extreme near-wall aspect ratio that makes the steady solve both slow (~1 h) AND numerically
# unstable (oscillatory divergence) for a LOADED airfoil — established over the turbulent campaigns.
# A coarse first cell (y+ ~ 25) with the all-y+ Spalding wall function removes the stiffness: GAMG
# converges in minutes and stays stable. The wall-function Cd bias (~+20%) is systematic and cancels
# in the matched-condition delta (the optimization product), so it does not weaken the improvement.
_FIRST_CELL = 1.0e-3
_N_SURFACE = 80
_N_NORMAL = 80
_N_FRONT = 40
_N_WAKE = 60


def _base_spec(
    name: str,
    *,
    aoa_deg: float,
    reynolds: float,
    max_camber: float,
    camber_position: float,
    end_time: int,
) -> CaseSpec:
    return CaseSpec(
        name=name,
        reynolds=reynolds,
        mach=0.15,
        aoa_deg=aoa_deg,
        turbulence_model="kOmegaSST",
        end_time=end_time,
        first_cell_height=_FIRST_CELL,  # y+ ~ 25 at Re=5e5 -> Spalding wall function (write_case)
        n_surface=_N_SURFACE,
        n_normal=_N_NORMAL,
        n_front=_N_FRONT,
        n_wake=_N_WAKE,
        # GAMG (pressure_solver None -> auto) is fast on the well-conditioned wall-function mesh.
        # The loaded airfoil limit-cycles in steady SIMPLE regardless of relaxation; its tail-MEAN
        # force is relaxation-independent (the reported value, via load_time_averaged). 0.7/0.5 gives
        # the SMALLEST fluctuation (~±2% baseline vs ~±35% at 0.3/0.2) → tightest mean + fastest.
        u_relax=0.7,
        kw_relax=0.5,
        max_camber=max_camber,
        camber_position=camber_position,
        # thickness fixed at NACA-0012 baseline for the 2-DV MVP (extensible to 3-DV).
    )


class ShapedTurbulentAirfoil:
    """Turbulent NACA-4 airfoil (k-omega SST, Re=3e6, fixed AoA) — L/D objective (Stage-15)."""

    sweep_metric = "ld"

    def __init__(
        self,
        spec: CaseSpec | None = None,
        *,
        name: str = "airfoil_opt_turb",
        aoa_deg: float = _BASE_AOA,
        reynolds: float = _BASE_RE,
        max_camber: float = 0.0,
        camber_position: float = 0.4,
        end_time: int = _BASE_END_TIME,
    ) -> None:
        self.name = name
        self._spec = spec or _base_spec(
            name,
            aoa_deg=aoa_deg,
            reynolds=reynolds,
            max_camber=max_camber,
            camber_position=camber_position,
            end_time=end_time,
        )
        self.description = (
            f"Turbulent NACA-4 airfoil (k-omega SST, Re={self._spec.reynolds:.2g}, "
            f"AoA={self._spec.aoa_deg} deg, m={self._spec.max_camber}, "
            f"p={self._spec.camber_position}) — L/D objective."
        )

    def case_spec(self) -> CaseSpec:
        return self._spec

    def reference(self, repo_root: Path) -> ReferenceData:
        # No absolute experiment anchor for an arbitrary shaped section — the optimizer reports a
        # matched-condition DELTA (systematic CFD bias cancels). Turbulent-RANS regime.
        return ReferenceData(
            case_name=self.name,
            source="matched-condition delta (no absolute anchor); turbulent RANS k-omega SST",
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        # L/D is the optimized scalar; no pass/fail band (the product is the delta, not an anchor).
        return (MetricSpec(name="ld", kind="scalar", tolerance=1.0e9, comparison="absolute"),)

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        # Loaded airfoils limit-cycle in steady SIMPLE; the tail-MEAN force is the (relaxation-
        # independent) converged value. Use the OpenFOAM tail-averaging load when available.
        load_avg = getattr(solver, "load_time_averaged", None)
        solve = load_avg(result)[0] if load_avg is not None else solver.load(result)
        if solve.cd is None or solve.cl is None:
            raise ValueError(
                f"{self.name}: SolveResult.cd/cl is None; the airfoil objective needs both "
                "force coefficients (Invariant 2 — FAIL-LOUD)."
            )
        if solve.cd <= 0.0:
            raise ValueError(f"{self.name}: non-positive cd ({solve.cd}); cannot form L/D.")
        return {"cd": solve.cd, "cl": solve.cl, "ld": solve.cl / solve.cd}

    def refined(self, ratio: float) -> ShapedTurbulentAirfoil:
        s = self._spec
        return ShapedTurbulentAirfoil(
            s.model_copy(
                update={
                    "n_surface": scaled_count(s.n_surface, ratio),
                    "n_normal": scaled_count(s.n_normal, ratio),
                    "n_front": scaled_count(s.n_front, ratio),
                    "n_wake": scaled_count(s.n_wake, ratio),
                }
            ),
            name=self.name,
        )

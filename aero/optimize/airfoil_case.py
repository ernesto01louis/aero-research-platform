"""The optimizer's forward airfoil case: a shaped laminar NACA-4 at fixed AoA (Stage 15).

Wraps the trusted `laminar_airfoil` regime (NACA 0012, Re=1000, steady laminar `simpleFoam` — the
only green + reliably-converging + cheap airfoil V&V case) with NACA-4 shape design variables
(`max_camber`, `camber_position`) and a positive angle of attack (so there is lift to improve).
Exposes ``lift_to_drag`` as the optimization objective and supports `refined()` for the
matched-grid GCI-on-the-delta. A `BenchmarkCase` (duck-typed), so it runs through the existing
`BenchmarkRunner` unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aero.adapters.openfoam.schemas import CaseSpec
from aero.optimize.mesh_family import graded_refined_spec
from aero.vv._base import MetricSpec, ReferenceData, Series, SolverLike, scaled_count

_BASE_AOA = (
    4.0  # positive incidence: lift to improve; well below the ~9 deg shedding onset at Re=1000
)


def _base_spec(name: str, *, aoa_deg: float, max_camber: float, camber_position: float) -> CaseSpec:
    return CaseSpec(
        name=name,
        reynolds=1.0e3,
        mach=0.1,
        aoa_deg=aoa_deg,
        turbulence_model="laminar",
        end_time=2000,
        first_cell_height=1.0e-3,
        max_camber=max_camber,
        camber_position=camber_position,
        # thickness fixed at the NACA-0012 baseline for the 2-DV MVP (extensible to 3-DV).
    )


class ShapedLaminarAirfoil:
    """Laminar NACA-4 airfoil at fixed AoA — objective = lift-to-drag ratio (Stage-15 optimizer)."""

    sweep_metric = "ld"

    def __init__(
        self,
        spec: CaseSpec | None = None,
        *,
        name: str = "airfoil_opt_naca4",
        aoa_deg: float = _BASE_AOA,
        max_camber: float = 0.0,
        camber_position: float = 0.4,
    ) -> None:
        self.name = name
        self._spec = spec or _base_spec(
            name, aoa_deg=aoa_deg, max_camber=max_camber, camber_position=camber_position
        )
        self.description = (
            f"Laminar NACA-4 airfoil (Re=1000, AoA={self._spec.aoa_deg} deg, "
            f"m={self._spec.max_camber}, p={self._spec.camber_position}) — L/D objective."
        )

    def case_spec(self) -> CaseSpec:
        return self._spec

    def reference(self, repo_root: Path) -> ReferenceData:
        # No absolute experiment anchor for a shaped section — the optimizer reports a
        # matched-condition DELTA, whose systematic CFD bias cancels. Kept minimal.
        return ReferenceData(
            case_name=self.name, source="matched-condition delta (no absolute anchor)"
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        # L/D is the optimized scalar; no pass/fail band (the product is the delta, not an anchor).
        return (MetricSpec(name="ld", kind="scalar", tolerance=1.0e9, comparison="absolute"),)

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        solve = solver.load(result)
        if solve.cd is None or solve.cl is None:
            raise ValueError(
                f"{self.name}: SolveResult.cd/cl is None; the airfoil objective needs both "
                "force coefficients (Invariant 2 — FAIL-LOUD)."
            )
        if solve.cd <= 0.0:
            raise ValueError(f"{self.name}: non-positive cd ({solve.cd}); cannot form L/D.")
        return {"cd": solve.cd, "cl": solve.cl, "ld": solve.cl / solve.cd}

    def refined(self, ratio: float, *, graded: bool = True) -> ShapedLaminarAirfoil:
        """A resolution-scaled copy: ratio > 1 coarsens, ratio < 1 refines.

        ``graded=True`` (Stage-16 default) refines on the FIXED stretching mapping — each
        direction's end-to-end expansion is pinned so first cells scale ~1/ratio and the
        family nests (a valid observed-order-GCI geometry). ``graded=False`` reproduces the
        Stage-15 count-only family (first cells pinned; the mapping drifts grid-to-grid) —
        kept for diagnostics and reproduction of the Stage-15 artifacts.
        """
        s = self._spec
        if graded:
            return ShapedLaminarAirfoil(graded_refined_spec(s, ratio), name=self.name)
        return ShapedLaminarAirfoil(
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

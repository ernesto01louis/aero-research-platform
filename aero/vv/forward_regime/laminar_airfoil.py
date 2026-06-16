"""Laminar NACA 0012 at Re = 1000 — forward-regime low-Re airfoil sanity.

A steady *laminar* NACA 0012 at AoA = 0, Re = 1000 — a low-Re baseline for the
regime the flapping optimizer operates in. Two checks:

* **symmetry (rigorous, reference-free):** a symmetric airfoil at zero incidence
  produces zero lift; a converged symmetric solve must return Cl ~= 0. This
  catches spurious asymmetry in mesh/solver with no external reference.
* **drag (low-Re literature sanity):** total Cd vs the canonical steady value
  Cd ~= 0.12 (Kurtuluş 2015, NACA 0012 at Re = 1000, AoA = 0 — steady; vortex
  shedding only onsets at AoA >= ~9 deg at this Re). Low-Re airfoil Cd carries a
  real code-to-code spread, so the tolerance is 10% (a documented contract, not
  a precision claim — transition modelling is Stage 13; this is the laminar
  baseline the ladder calls for).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aero.adapters.openfoam.schemas import CaseSpec
from aero.vv._base import (
    MetricSpec,
    ReferenceData,
    Series,
    SolverLike,
    load_scalar_csv,
    scaled_count,
)


class LaminarAirfoil:
    """Laminar NACA 0012 (Re = 1000, AoA = 0) — low-Re Cd + symmetry sanity."""

    name = "laminar_airfoil_naca0012"
    description = (
        "Laminar NACA 0012 at Re=1000 (forward-regime low-Re airfoil: Cd + Cl=0 symmetry)."
    )
    sweep_metric = "cd"

    def __init__(self, spec: CaseSpec | None = None) -> None:
        self._spec = spec or CaseSpec(
            name=self.name,
            reynolds=1.0e3,  # steady laminar at AoA=0 (shedding onsets at AoA>=~9 deg)
            mach=0.1,
            aoa_deg=0.0,
            turbulence_model="laminar",
            end_time=2000,
            # Thick laminar BL (delta ~ 0.1-0.3c): a far coarser first cell than
            # the high-Re y+<1 default, to avoid pointless near-wall aspect ratio.
            first_cell_height=1.0e-3,
            # Sharp TE (the blunt-TE C-grid is the rejected NACA remedy, Stage-10).
        )

    def case_spec(self) -> CaseSpec:
        return self._spec

    def reference(self, repo_root: Path) -> ReferenceData:
        cd = load_scalar_csv(
            repo_root
            / "data"
            / "references"
            / "forward_regime"
            / "laminar_airfoil_naca0012"
            / "cd.csv",
            key_col="aoa_deg",
            key=0.0,
            value_col="cd",
        )
        return ReferenceData(
            case_name=self.name,
            source="Kurtuluş (2015), NACA 0012 Re=1000 AoA=0 steady Cd; Cl=0 by symmetry",
            scalars={"cd": cd, "cl": 0.0},
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        return (
            # Lift: exactly zero by symmetry — absolute tolerance (relative would
            # divide by the zero reference). A rigorous solution-quality check.
            MetricSpec(name="cl", kind="scalar", tolerance=0.01, comparison="absolute"),
            # Drag: vs the low-Re literature value, with a documented 10% band.
            MetricSpec(name="cd", kind="scalar", tolerance=0.10, comparison="relative"),
        )

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        solve = solver.load(result)
        if solve.cd is None or solve.cl is None:
            raise ValueError(
                f"{self.name}: SolveResult.cd/cl is None; a laminar airfoil case "
                "requires both force coefficients (Invariant 2 — FAIL-LOUD)."
            )
        return {"cd": solve.cd, "cl": solve.cl}

    def refined(self, ratio: float) -> LaminarAirfoil:
        s = self._spec
        return LaminarAirfoil(
            s.model_copy(
                update={
                    "n_surface": scaled_count(s.n_surface, ratio),
                    "n_normal": scaled_count(s.n_normal, ratio),
                    "n_front": scaled_count(s.n_front, ratio),
                    "n_wake": scaled_count(s.n_wake, ratio),
                }
            )
        )

"""The NASA TMR NACA 0012 drag-verification case.

NACA 0012 at Re = 6e6, AoA = 0 deg. The metric is total drag Cd, compared
(3%, ADR-005) against the TMR grid-converged reference. The honest Cd to judge
is the Richardson-extrapolated value from a three-grid `MeshSweep` — the
`refined()` method below scales the C-grid resolution for that sweep.
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


class NACA0012Verification:
    """NACA 0012 (Re = 6e6, AoA = 0 deg) — drag-coefficient verification."""

    name = "naca0012_verification"
    description = "NASA TMR NACA 0012 — drag-coefficient (Cd) verification, with a GCI sweep."
    sweep_metric = "cd"

    def __init__(self, spec: CaseSpec | None = None) -> None:
        self._spec = spec or CaseSpec(
            name=self.name,
            reynolds=6.0e6,
            mach=0.15,
            aoa_deg=0.0,
            end_time=3000,
            # Stage-09 blunt-TE hardening (ADR-012): a finite open TE splits the
            # singular sharp-TE vertex that produced the +21% pressure drag. The
            # xfail flips to a strict pass once the cluster mesh-sweep confirms
            # the new mesh is valid AND Cd is within 3%.
            trailing_edge_thickness=0.0025,
            n_te=8,
        )

    def case_spec(self) -> CaseSpec:
        return self._spec

    def reference(self, repo_root: Path) -> ReferenceData:
        # Stage 05 verifies AoA = 0 deg.
        cd = load_scalar_csv(
            repo_root / "data" / "references" / "tmr" / "naca0012" / "cd.csv",
            key_col="aoa_deg",
            key=0.0,
            value_col="cd",
        )
        return ReferenceData(
            case_name=self.name,
            source="NASA TMR NACA 0012 grid-converged k-omega SST drag",
            scalars={"cd": cd},
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        return (MetricSpec(name="cd", kind="scalar", tolerance=0.03, comparison="relative"),)

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        solve = solver.load(result)
        if solve.cd is None:
            raise ValueError(
                f"{self.name}: SolveResult.cd is None; an airfoil verification case "
                "requires a converged drag coefficient (Invariant 2 — FAIL-LOUD)."
            )
        return {"cd": solve.cd}

    def refined(self, ratio: float) -> NACA0012Verification:
        s = self._spec
        return NACA0012Verification(
            s.model_copy(
                update={
                    "n_surface": scaled_count(s.n_surface, ratio),
                    "n_normal": scaled_count(s.n_normal, ratio),
                    "n_front": scaled_count(s.n_front, ratio),
                    "n_wake": scaled_count(s.n_wake, ratio),
                    "n_te": scaled_count(s.n_te, ratio) if s.n_te else 0,
                }
            )
        )

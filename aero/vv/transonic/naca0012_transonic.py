"""Transonic NACA 0012 — Cd vs the AGARD-AR-138 / Schmitt-Charpin reference.

Stage 06 (ADR-006): the platform's first compressible case. The SU2-native
`SU2AirfoilSpec` generates an O-grid; SU2 runs `RANS` at M=0.7, AoA=1.49°,
Re ≈ 9e6, and the converged Cd is compared against the published transonic
reference (5% tolerance — looser than the TMR 3% because experimental
transonic data carries larger scatter and the SU2 mesh quality on the first
build will not yet be the converged-Cd grid).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aero.adapters.su2.schemas import SU2AirfoilSpec
from aero.vv._base import (
    MetricSpec,
    ReferenceData,
    Series,
    SolverLike,
    load_scalar_csv,
)


class NACA0012Transonic:
    """NACA 0012, M = 0.7, AoA = 1.49 deg — transonic Cd verification (SU2-only)."""

    name = "naca0012_transonic"
    description = (
        "Transonic NACA 0012 (M=0.7, AoA=1.49 deg) — Cd vs AGARD-AR-138 / "
        "Schmitt-Charpin reference (5% tolerance, ADR-006)."
    )
    sweep_metric = "cd"

    def __init__(self, spec: SU2AirfoilSpec | None = None) -> None:
        self._spec = spec or SU2AirfoilSpec(
            name=self.name,
            mach=0.7,
            aoa_deg=1.49,
            reynolds=9.0e6,
            turbulence_model="SA",
            iterations=8000,
            cfl=5.0,
            n_surface=240,
            n_normal=140,
            farfield_radius_chords=50.0,
            first_cell_height=1.0e-6,
        )

    def case_spec(self) -> SU2AirfoilSpec:
        return self._spec

    def reference(self, repo_root: Path) -> ReferenceData:
        cd = load_scalar_csv(
            repo_root / "data" / "references" / "transonic" / "naca0012_transonic" / "cd.csv",
            key_col="aoa_deg",
            key=1.49,
            value_col="cd",
        )
        return ReferenceData(
            case_name=self.name,
            source="AGARD-AR-138 / Schmitt-Charpin transonic NACA 0012 (M=0.7, AoA=1.49 deg)",
            scalars={"cd": cd},
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        return (MetricSpec(name="cd", kind="scalar", tolerance=0.05, comparison="relative"),)

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        solve = solver.load(result)
        if solve.cd is None:
            raise ValueError(
                f"{self.name}: SolveResult.cd is None; a transonic airfoil case "
                "requires a converged drag coefficient (Invariant 2 — FAIL-LOUD)."
            )
        return {"cd": solve.cd}

    def refined(self, ratio: float) -> NACA0012Transonic:
        from aero.vv._base import scaled_count

        s = self._spec
        return NACA0012Transonic(
            s.model_copy(
                update={
                    "n_surface": scaled_count(s.n_surface, ratio, minimum=8),
                    "n_normal": scaled_count(s.n_normal, ratio),
                }
            )
        )

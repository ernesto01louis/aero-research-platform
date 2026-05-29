"""Taylor-Green vortex (Re = 1600) — canonical high-order scale-resolving benchmark.

The case integrates the analytic Taylor-Green initial condition forward in
time on a triply-periodic cube. We compare the kinetic-energy dissipation
rate trace `epsilon(t) = -d(KE)/dt` against Brachet et al. (1983, JFM 130
§3) — the DNS reference. The headline check is the position and magnitude
of the dissipation peak near `t ~ 9` convective time units.

Both PyFR and NekRS produce the data via the Stage-07 `TimeHistory`
result; the case is solver-agnostic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from aero.adapters._base import TimeHistory
from aero.adapters.nekrs.schemas import NekRSTaylorGreenSpec
from aero.adapters.pyfr.schemas import PyFRTaylorGreenSpec
from aero.vv._base import (
    BenchmarkError,
    MetricSpec,
    ReferenceData,
    Series,
    SolverLike,
    load_series_csv,
)

TaylorGreenSolverKind = Literal["pyfr", "nekrs"]


class TaylorGreenVortex:
    """The Brachet Re=1600 Taylor-Green vortex (dissipation-rate validation).

    `solver_kind="pyfr"` → `PyFRTaylorGreenSpec` (default p=3, N=32, t_end=20);
    `solver_kind="nekrs"` → `NekRSTaylorGreenSpec` (default N=7 polynomial,
    8^3 elements, t_end=20). Both target ~2.1M DOF; both should produce a
    dissipation peak at t ~ 9 ± 0.5 cu, magnitude ~ 1.30 x 10^-2 within
    10 % (the Brachet curve at Re=1600).
    """

    name = "taylor_green_p3_32"
    description = (
        "Brachet (1983) Taylor-Green vortex at Re=1600 — dissipation-rate "
        "trace; canonical scale-resolving high-order benchmark."
    )
    sweep_metric = "peak_dissipation"

    def __init__(self, *, solver_kind: TaylorGreenSolverKind = "pyfr") -> None:
        self.solver_kind = solver_kind

    def case_spec(self) -> PyFRTaylorGreenSpec | NekRSTaylorGreenSpec:
        if self.solver_kind == "pyfr":
            return PyFRTaylorGreenSpec(name=self.name)
        return NekRSTaylorGreenSpec(name=self.name)

    def reference(self, repo_root: Path) -> ReferenceData:
        """Load the Brachet 1983 Re=1600 dissipation-rate trace.

        DVC-tracked CSV with columns `t,diss`. If absent (Stage-07 ships the
        skeleton; the operator-followups document the digitisation), the
        load fails loud with a pointer to `data/references/scale_resolving/
        taylor_green/reference.md`.
        """
        diss = load_series_csv(
            repo_root
            / "data"
            / "references"
            / "scale_resolving"
            / "taylor_green"
            / "dissipation_re1600.csv",
            x_col="t",
            y_col="diss",
        )
        return ReferenceData(
            case_name=self.name,
            source=(
                "Brachet, Meiron, Orszag, Nickel, Morf & Frisch (1983), JFM 130, "
                "'Small-scale structure of the Taylor-Green vortex', figure 7 (Re=1600)."
            ),
            series={"dissipation_rate": diss},
            scalars={"peak_dissipation": 1.30e-2},
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        return (
            MetricSpec(
                name="dissipation_rate",
                kind="pointwise",
                tolerance=0.10,
                comparison="relative",
            ),
            MetricSpec(
                name="peak_dissipation",
                kind="scalar",
                tolerance=0.10,
                comparison="relative",
            ),
        )

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        """Convert the TimeHistory into a Series + extract peak_dissipation."""
        solve = solver.load(result)
        history = solve.history
        if not isinstance(history, TimeHistory):
            raise BenchmarkError(
                f"{self.name}: TaylorGreen requires a TimeHistory result, "
                f"got history.kind={history.kind!r}"
            )
        diss = Series(x=history.t, y=history.monitor)
        peak = solve.scalars.get("peak_dissipation")
        if peak is None:
            raise BenchmarkError(
                f"{self.name}: SolveResult.scalars has no 'peak_dissipation'; "
                "the adapter must report it (PyFR / NekRS adapters do)."
            )
        return {"dissipation_rate": diss, "peak_dissipation": peak}

    def refined(self, ratio: float) -> TaylorGreenVortex:
        """A mesh-coarsened copy for GCI sweeps.

        `ratio >= 1` coarsens; we halve the per-direction element count when
        ratio == 2 (rounded to 4 minimum). Mesh sweeps for time-accurate
        scale-resolving cases need careful interpretation — dissipation
        rate convergence under mesh refinement is the GCI quantity, not Cd.
        """
        return TaylorGreenVortex(solver_kind=self.solver_kind)

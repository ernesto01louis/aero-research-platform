"""Low-Re cylinder vortex shedding — forward-regime Strouhal verification.

A circular cylinder at Re = 100 sheds a laminar von Kármán street. The canonical
verification is the Strouhal number St = f D / U (f = shedding frequency) against
the Roshko/Williamson St-Re relation: St ~= 0.165 at Re = 100. This is the
platform's first *transient* OpenFOAM case (`pimpleFoam`), exercising the
unsteady machinery the flapping mission ultimately depends on.

The solve logs Cl(t); the loader (`aero.adapters.openfoam.solver`) FFTs the
saturated tail to recover the shedding frequency and reports St in
`SolveResult.scalars["strouhal"]`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aero.adapters.openfoam.cylinder import CylinderSpec
from aero.vv._base import (
    MetricSpec,
    ReferenceData,
    Series,
    SolverLike,
    load_scalar_csv,
    scaled_count,
)


class CylinderStrouhal:
    """Laminar cylinder at Re = 100 — vortex-shedding Strouhal verification (transient)."""

    name = "cylinder_strouhal_re100"
    description = (
        "Low-Re cylinder (Re=100) vortex-shedding Strouhal vs the Roshko/Williamson St-Re."
    )
    sweep_metric = "strouhal"

    def __init__(self, spec: CylinderSpec | None = None) -> None:
        self._spec = spec or CylinderSpec(name=self.name, reynolds=100.0)

    def case_spec(self) -> CylinderSpec:
        return self._spec

    def reference(self, repo_root: Path) -> ReferenceData:
        st = load_scalar_csv(
            repo_root
            / "data"
            / "references"
            / "forward_regime"
            / "cylinder_strouhal_re100"
            / "strouhal.csv",
            key_col="reynolds",
            key=100.0,
            value_col="strouhal",
        )
        return ReferenceData(
            case_name=self.name,
            source="Roshko/Williamson St-Re relation; St~=0.165 at Re=100",
            scalars={"strouhal": st},
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        return (MetricSpec(name="strouhal", kind="scalar", tolerance=0.05, comparison="relative"),)

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        solve = solver.load(result)
        st = solve.scalars.get("strouhal")
        if st is None:
            raise ValueError(
                f"{self.name}: SolveResult.scalars['strouhal'] missing — the transient "
                "loader did not extract a shedding frequency (did the cylinder shed?)."
            )
        return {"strouhal": st}

    def refined(self, ratio: float) -> CylinderStrouhal:
        s = self._spec
        return CylinderStrouhal(
            s.model_copy(
                update={
                    "n_radial": scaled_count(s.n_radial, ratio),
                    "n_azimuthal": scaled_count(s.n_azimuthal, ratio),
                }
            )
        )

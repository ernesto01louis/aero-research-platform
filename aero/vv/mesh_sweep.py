"""ASME V&V 20 grid-convergence (GCI) automation.

`MeshSweep` runs one `BenchmarkCase` at three mesh resolutions and reports the
Grid Convergence Index per ASME V&V 20-2009 / Celik et al. (2008,
"Procedure for Estimation and Reporting of Uncertainty Due to Discretization
in CFD Applications", J. Fluids Eng. 130(7)).

The GCI gives the order of accuracy observed from three grids, the
Richardson-extrapolated grid-converged value, and an uncertainty band on the
fine-grid result — the numbers a methods section must report for a result to
be citable. This is the bedrock primitive every publish-quality run reuses.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aero.provenance.four_fold import ProvenanceTuple
from aero.vv._base import BenchmarkCase, BenchmarkError, BenchmarkRunner

_STRICT = ConfigDict(extra="forbid", frozen=True, validate_default=True)

# ASME V&V 20 factor of safety for a GCI computed from three or more grids.
_FACTOR_OF_SAFETY = 1.25


class GridPoint(BaseModel):
    """One grid in a sweep: its refinement ratio, size, and the metric value."""

    model_config = _STRICT

    refinement_ratio: float = Field(..., ge=1.0, description="1.0 is the finest grid.")
    n_cells: int = Field(..., gt=0, description="Total mesh cell count.")
    representative_h: float = Field(..., gt=0, description="Representative grid size, ~N^-1/2.")
    metric_value: float = Field(..., description="The swept scalar metric on this grid.")
    mlflow_run_id: str | None = Field(default=None)


class SweepReport(BaseModel):
    """A grid-convergence study: the three grids and the derived GCI numbers."""

    model_config = _STRICT

    case_name: str = Field(..., min_length=1)
    metric: str = Field(..., min_length=1)
    grids: tuple[GridPoint, GridPoint, GridPoint] = Field(..., description="Fine to coarse.")
    observed_order_p: float = Field(..., description="Observed order of accuracy.")
    extrapolated_value: float = Field(..., description="Richardson-extrapolated (h->0) value.")
    gci_fine_pct: float = Field(..., ge=0, description="Fine-grid GCI, percent.")
    apparent_uncertainty: float = Field(
        ..., ge=0, description="Uncertainty band on the fine-grid value (fraction)."
    )
    monotonic: bool = Field(..., description="True iff the three grids converge monotonically.")

    def to_json(self) -> str:
        """Serialise the sweep report to JSON."""
        return self.model_dump_json(indent=2)


def _observed_order(r21: float, r32: float, e21: float, e32: float) -> tuple[float, bool]:
    """Solve the ASME V&V 20 transcendental equation for the observed order p.

    Returns `(p, monotonic)`. `monotonic` is False for an oscillatory triple
    (the ratio of successive differences is negative) — a non-monotone sweep
    does not yield a strictly valid GCI and the caller must flag it.
    """
    if e21 == 0.0:
        raise BenchmarkError("grid-convergence: the two finest grids gave identical values")
    ratio = e32 / e21
    s = 1.0 if ratio > 0.0 else -1.0
    monotonic = s > 0.0
    ln_r21 = math.log(r21)
    abs_ln_ratio = abs(math.log(abs(ratio)))

    p = abs_ln_ratio / ln_r21  # initial guess (q = 0)
    for _ in range(200):
        q = math.log((r21**p - s) / (r32**p - s))
        p_new = abs(abs_ln_ratio + q) / ln_r21
        if abs(p_new - p) < 1.0e-9:
            return p_new, monotonic
        p = p_new
    raise BenchmarkError("grid-convergence: observed-order iteration did not converge")


def grid_convergence_index(
    grids: tuple[GridPoint, GridPoint, GridPoint],
) -> tuple[float, float, float, bool]:
    """Compute `(observed_order_p, extrapolated_value, gci_fine, monotonic)`.

    `grids` is ordered fine -> coarse. `gci_fine` is a fraction (multiply by
    100 for a percentage). Per Celik et al. (2008), GCI_fine uses the
    factor-of-safety 1.25 appropriate to a three-grid study.
    """
    g1, g2, g3 = grids  # fine, medium, coarse
    h1, h2, h3 = g1.representative_h, g2.representative_h, g3.representative_h
    if not (h1 < h2 < h3):
        raise BenchmarkError("grid-convergence: grids are not strictly fine -> coarse")
    phi1, phi2, phi3 = g1.metric_value, g2.metric_value, g3.metric_value

    r21, r32 = h2 / h1, h3 / h2
    e21, e32 = phi2 - phi1, phi3 - phi2
    p, monotonic = _observed_order(r21, r32, e21, e32)

    r21p = r21**p
    extrapolated = (r21p * phi1 - phi2) / (r21p - 1.0)
    if phi1 == 0.0:
        raise BenchmarkError("grid-convergence: fine-grid value is zero")
    e_a21 = abs((phi1 - phi2) / phi1)
    gci_fine = _FACTOR_OF_SAFETY * e_a21 / (r21p - 1.0)
    return p, extrapolated, gci_fine, monotonic


class MeshSweep:
    """Runs a `BenchmarkCase` at three resolutions and computes its GCI."""

    def __init__(
        self,
        base_case: BenchmarkCase,
        *,
        metric: str = "cd",
        refinement_ratios: tuple[float, float, float] = (1.0, 1.3, 1.7),
    ) -> None:
        if sorted(refinement_ratios) != list(refinement_ratios):
            raise ValueError("refinement_ratios must be ascending (1.0 is the finest grid)")
        if refinement_ratios[0] != 1.0:
            raise ValueError("the finest refinement ratio must be 1.0 (the base case)")
        self.base_case = base_case
        self.metric = metric
        self.refinement_ratios = refinement_ratios

    def run(
        self, runner: BenchmarkRunner, *, provenance: ProvenanceTuple, repo_root: Any
    ) -> SweepReport:
        """Solve the base case at each refinement ratio and build the GCI report.

        A GCI is a *verification* study — it compares a solution against itself
        at three resolutions — so each grid is measured via `measure_scalar`,
        which needs no (validation) reference data.
        """
        points: list[GridPoint] = []
        for ratio in self.refinement_ratios:
            case = self.base_case.refined(ratio)
            obs = runner.measure_scalar(
                case, self.metric, provenance=provenance, repo_root=repo_root
            )
            if obs.n_elements is None or obs.n_elements <= 0:
                raise BenchmarkError("mesh sweep needs a reported element count from each grid")
            points.append(
                GridPoint(
                    refinement_ratio=ratio,
                    # `GridPoint.n_cells` keeps the GCI-domain naming convention
                    # (ASME V&V 20 §"cell count") even though it is sourced from
                    # the Stage-07 renamed `obs.n_elements` (FV cells for
                    # OpenFOAM/SU2, FR/SEM elements for PyFR/NekRS).
                    n_cells=obs.n_elements,
                    # 2D representative size: h ~ (1/N)^(1/2); the constant
                    # area factor cancels in every ratio that GCI uses.
                    representative_h=(1.0 / obs.n_elements) ** 0.5,
                    metric_value=obs.value,
                    mlflow_run_id=obs.mlflow_run_id,
                )
            )

        grids = (points[0], points[1], points[2])
        p, extrapolated, gci_fine, monotonic = grid_convergence_index(grids)
        return SweepReport(
            case_name=self.base_case.name,
            metric=self.metric,
            grids=grids,
            observed_order_p=p,
            extrapolated_value=extrapolated,
            gci_fine_pct=gci_fine * 100.0,
            apparent_uncertainty=gci_fine,
            monotonic=monotonic,
        )

"""Attribute a coupled run's wall clock to the work that caused it — ADR-040's evidence.

Handoff §6.29 listed four candidate cost terms for the measured 16.08 s/window (serial
PIMPLE, adapter checkpointing, preCICE exchange, ``forces1``'s per-step NFS writes) and
said plainly that none of them was separately measured. This module measures them, from
the ``FluidCostHistory`` that ``aero.adapters.openfoam.solver_log`` reads out of a log a
completed run already wrote.

The model is deliberately the simplest thing that can be falsified::

    d_execution_s  ~  sum_g c_g * iterations_g  +  b

One coefficient per named *group* of solved fields (``p`` and ``pcorr`` are one pressure
regressor; the momentum components are another), plus an intercept. The intercept is the
load-bearing term, not a nuisance: everything that happens once per step and does not
scale with linear-solver iterations — the function-object writes, the preCICE exchange,
the adapter's checkpoint, matrix assembly — lands in it. So ``intercept_share`` is an
upper bound on every cost lever that attacks per-step overhead rather than the solve,
and a lever whose ceiling is below the speed-up being sought is refuted without being
tried.

Two refusals, both because the alternative is a plausible number rather than an error:

* a **rank-deficient** design matrix means the groups are not separately identifiable
  (two regressors that move together in the record), and least squares would return one
  arbitrary split out of an infinite family. It raises.
* **too few steps** for the regressor count is a fit, not a measurement.

Negative coefficients are recorded, never clipped: a negative cost per iteration means
the model does not describe the run, and hiding it would let a bad fit read as a good one.

Stdlib + numpy + pydantic only (Invariant 1). Pure — no filesystem, no clocks.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from aero.adapters.openfoam.solver_log import FluidCostHistory

__all__ = ["CostAttribution", "CostModelError", "attribute_step_cost"]

#: Least-squares needs headroom over the parameter count before a fit means anything.
#: One step per parameter interpolates exactly and reports R^2 = 1 on noise.
_MIN_STEPS_OVER_PARAMETERS = 2


class CostModelError(Exception):
    """The record cannot support the attribution being asked of it; the reason is the message."""


class CostAttribution(BaseModel):
    """Where a fluid participant's CPU went, as coefficients and as shares."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    n_steps: int = Field(..., ge=1)
    mean_seconds_per_step: float = Field(..., gt=0.0)
    seconds_per_iteration_by_group: dict[str, float] = Field(
        ..., description="Fitted marginal cost of one linear-solver iteration in the group."
    )
    mean_iterations_by_group: dict[str, float] = Field(...)
    intercept_s: float = Field(
        ...,
        description=(
            "Per-step cost that does not scale with solver iterations: function-object "
            "writes, preCICE exchange, checkpointing, assembly."
        ),
    )
    share_by_group: dict[str, float] = Field(...)
    intercept_share: float = Field(
        ...,
        description=(
            "Upper bound on every lever that attacks per-step overhead instead of the "
            "solve. A lever whose ceiling is below the speed-up sought is refuted."
        ),
    )
    r_squared: float = Field(..., description="Fit quality; a low value means the model is wrong.")

    def dominant_group(self) -> str:
        """The group carrying the largest share — where a speed-up has to come from."""
        return max(self.share_by_group, key=lambda g: self.share_by_group[g])


def attribute_step_cost(
    history: FluidCostHistory, *, groups: Mapping[str, Sequence[str]]
) -> CostAttribution:
    """Regress per-step CPU on per-step linear-solver iterations, one group at a time.

    ``groups`` maps a regressor name to the solved fields it folds together, e.g.
    ``{"gamg_pressure": ("p", "pcorr"), "momentum": ("Ux", "Uy")}``. A field absent from
    the log contributes zero iterations rather than raising — the vocabulary belongs to
    the run, and a numerics candidate that drops a field is a legitimate comparison.
    """
    if not groups:
        raise CostModelError("no regressor groups given — there is nothing to attribute cost to")

    names = tuple(groups)
    n_parameters = len(names) + 1  # + the intercept
    if history.n_steps < n_parameters + _MIN_STEPS_OVER_PARAMETERS:
        raise CostModelError(
            f"{history.n_steps} steps cannot support {n_parameters} parameters: a fit with "
            "as many observations as parameters interpolates its own noise and reports a "
            "perfect R^2. This is a fit, not a measurement"
        )

    columns = [history.iterations_per_step(*groups[name]) for name in names]
    design = np.column_stack([*columns, np.ones(history.n_steps, dtype=np.float64)])
    if np.linalg.matrix_rank(design) < n_parameters:
        raise CostModelError(
            f"the design matrix for groups {names} is rank-deficient: at least two "
            "regressors move together across every step in this record, so their split is "
            "not identifiable and least squares would return one arbitrary answer out of "
            "an infinite family. Merge them into one group, or measure a record in which "
            "they vary independently"
        )

    y = history.d_execution()
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    predicted = design @ coefficients
    total_variance = float(((y - y.mean()) ** 2).sum())
    residual = float(((y - predicted) ** 2).sum())
    r_squared = 1.0 - residual / total_variance if total_variance > 0.0 else 1.0

    mean_step = float(y.mean())
    if mean_step <= 0.0:
        raise CostModelError(
            f"the mean per-step CPU is {mean_step!r} s — a record with no measurable cost "
            "cannot be attributed"
        )
    mean_iterations = {
        name: float(column.mean()) for name, column in zip(names, columns, strict=True)
    }
    per_iteration = {name: float(coefficients[i]) for i, name in enumerate(names)}
    # Shares partition unity EXACTLY: a least-squares fit carrying an intercept forces the
    # residuals to sum to zero, so mean(y) == mean(prediction). That identity is what makes
    # `intercept_share` a bound rather than an estimate.
    shares = {name: per_iteration[name] * mean_iterations[name] / mean_step for name in names}
    return CostAttribution(
        n_steps=history.n_steps,
        mean_seconds_per_step=mean_step,
        seconds_per_iteration_by_group=per_iteration,
        mean_iterations_by_group=mean_iterations,
        intercept_s=float(coefficients[-1]),
        share_by_group=shares,
        intercept_share=float(coefficients[-1]) / mean_step,
        r_squared=r_squared,
    )

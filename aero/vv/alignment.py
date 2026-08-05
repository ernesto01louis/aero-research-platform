"""Prove two arms of a paired comparison are actually comparable — before differencing them.

A matched-condition delta only cancels correlated error if the two runs really are matched.
``paired_delta_uncertainty`` checks what it can see (the periods, the cycle counts), but by
the time it is called both records have been reduced to per-cycle means, and the ways two
arms drift apart are mostly invisible at that point:

* **Different time bases.** The flexible and rigid arms run the same prescribed motion at
  the same fixed ``dt``, so their sample times are the same numbers, written by the same
  code at the same precision. If they are not, one arm dropped or gained samples --
  ``force_io`` de-duplicates collapsed timestamps -- and index-``k`` pairing is comparing
  different instants. This is the one place bitwise equality is the RIGHT test: not across
  an ASCII round trip between two independent accumulators, but between two runs of one
  writer on one prescribed schedule.
* **Different segmentation periods.** Two independently detected periods never agree to
  nine digits, and cycle boundaries then drift relative to each other across the window, so
  the per-cycle difference series measures the drift.
* **Different anchors.** The arms generally settle at different cycles. That is handled --
  by taking the later anchor -- but only if both series are anchored at the same origin to
  begin with.

Each of those is checked here, loudly, with the arithmetic that shows what went wrong.

The module also owns the per-cycle efficiency series, because efficiency is the one gated
quantity that is a RATIO. ``eta`` is a ratio of means, never a mean of ratios: see
:func:`per_cycle_efficiency`.

stdlib + numpy + pydantic only.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from aero.postprocess.limit_cycle import LimitCycleAnalysis

__all__ = [
    "AlignedPair",
    "AlignmentError",
    "align_arms",
    "assert_common_time_base",
    "per_cycle_efficiency",
    "window_efficiency",
]

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)


class AlignmentError(RuntimeError):
    """Two arms of a paired comparison are not comparable."""


class AlignedPair(BaseModel):
    """The common window two aligned arms share, and the evidence that they are aligned."""

    model_config = _STRICT

    period: float = Field(..., gt=0.0, description="The one period both arms were segmented on.")
    pair_start: int = Field(
        ...,
        ge=0,
        description="First paired cycle index: the LATER of the two arms' converged anchors.",
    )
    n_pairs: int = Field(..., ge=1, description="Cycles in the common converged window.")
    baseline_anchor: int = Field(..., ge=0)
    candidate_anchor: int = Field(..., ge=0)
    n_samples: int = Field(..., ge=2, description="Raw samples on the shared time base.")


def assert_common_time_base(
    baseline_t: NDArray[np.float64],
    candidate_t: NDArray[np.float64],
    *,
    what: str = "the two arms",
) -> None:
    """Refuse unless the two arms were sampled at BITWISE-identical instants.

    Both arms run the same prescribed motion at the same fixed ``deltaT``, written by one
    writer at one ``timePrecision``, so their time columns are the same doubles. Anything
    else means a sample was dropped or added on one side -- which is exactly what
    ``force_io``'s de-duplication does when ``timePrecision`` is too coarse -- and every
    per-cycle mean downstream is then built from a different set of instants on each arm.
    """
    a = np.asarray(baseline_t, dtype=np.float64)
    b = np.asarray(candidate_t, dtype=np.float64)
    if a.shape != b.shape:
        raise AlignmentError(
            f"{what} have different sample counts: {a.size} vs {b.size}. Matched-condition "
            "runs share one fixed time step and one end time, so a difference means one "
            "record is short (did a run hit its ceiling?) or rows were dropped (raise "
            "timePrecision; read_force_history reports n_dropped)."
        )
    if a.size < 2:
        raise AlignmentError(f"{what}: fewer than two samples — nothing to align")
    if not np.array_equal(a, b):
        differing = int(np.count_nonzero(a != b))
        first = int(np.argmax(a != b))
        raise AlignmentError(
            f"{what} are not sampled at the same instants: {differing} of {a.size} times "
            f"differ, first at index {first} ({a[first]!r} vs {b[first]!r}). Index-k cycle "
            "pairing compares different instants, so the paired difference would measure "
            "the offset rather than the physics."
        )


def align_arms(
    baseline: LimitCycleAnalysis,
    candidate: LimitCycleAnalysis,
    *,
    baseline_t: NDArray[np.float64] | None = None,
    candidate_t: NDArray[np.float64] | None = None,
) -> AlignedPair:
    """Check every way two arms can fail to be comparable, then report the common window.

    `baseline_t` / `candidate_t` are the RAW sample times. They are optional only because
    an analysis does not carry them; pass them whenever they exist, which for the Stage-20
    readout is always.
    """
    if baseline.period_source != "prescribed" or candidate.period_source != "prescribed":
        raise AlignmentError(
            "a paired comparison must segment BOTH arms on the prescribed period "
            f"(baseline: {baseline.period_source}, candidate: {candidate.period_source}). "
            "Two independently detected periods cannot agree to the 1e-9 the paired "
            "estimator requires, and their cycle boundaries drift apart across the window."
        )
    if baseline.period != candidate.period:
        raise AlignmentError(
            f"the arms were segmented on different periods: {baseline.period!r} vs "
            f"{candidate.period!r}. Prescribed periods come from one motion spec and must "
            "be the same float."
        )
    if baseline.discard_s != candidate.discard_s:
        raise AlignmentError(
            f"the arms discard different start-up windows ({baseline.discard_s!r} vs "
            f"{candidate.discard_s!r}), so their cycle indices count from different "
            "origins and index-k pairing is meaningless."
        )
    if baseline_t is not None and candidate_t is not None:
        assert_common_time_base(baseline_t, candidate_t)

    start = max(
        baseline.convergence.converged_from_cycle, candidate.convergence.converged_from_cycle
    )
    end = min(baseline.convergence.n_cycles, candidate.convergence.n_cycles)
    if end - start < 1:
        raise AlignmentError(
            f"the arms' converged tails do not overlap: baseline settles at cycle "
            f"{baseline.convergence.converged_from_cycle} of "
            f"{baseline.convergence.n_cycles}, candidate at "
            f"{candidate.convergence.converged_from_cycle} of "
            f"{candidate.convergence.n_cycles}. Extend BOTH runs."
        )
    n_samples = 2 if baseline_t is None else int(np.asarray(baseline_t).size)
    return AlignedPair(
        period=baseline.period,
        pair_start=start,
        n_pairs=end - start,
        baseline_anchor=baseline.convergence.converged_from_cycle,
        candidate_anchor=candidate.convergence.converged_from_cycle,
        n_samples=n_samples,
    )


def per_cycle_efficiency(
    thrust_per_cycle: NDArray[np.float64],
    power_per_cycle: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Per-cycle propulsive efficiency ``eta_k = <C_T>_k / <C_P>_k``.

    **A ratio of means, per cycle — never a mean of ratios.** The distinction is not
    pedantry: efficiency is defined on cycle-mean thrust over cycle-mean power (the thesis
    nomenclature, ``eta = Ct/Cp``), and averaging instantaneous ratios instead would weight
    the parts of the stroke where the power passes through zero arbitrarily heavily and
    produce a number with no physical definition. Each element here is one cycle's mean
    thrust divided by that same cycle's mean power; the WINDOW efficiency is then
    :func:`window_efficiency`, which is again a ratio of means and NOT the mean of this
    array.

    This series exists so the D2/D4 efficiency clauses can go through the paired path,
    which needs a per-cycle series to difference.
    """
    thrust = np.asarray(thrust_per_cycle, dtype=np.float64)
    power = np.asarray(power_per_cycle, dtype=np.float64)
    if thrust.shape != power.shape:
        raise AlignmentError(
            f"thrust and power cover different cycle counts ({thrust.size} vs {power.size})"
        )
    if thrust.size == 0:
        raise AlignmentError("no cycles to compute an efficiency over")
    if np.any(power == 0.0):
        raise AlignmentError(
            "a cycle-mean power of exactly zero — efficiency is undefined there, and "
            "substituting a large number or a nan would put it into a gated statistic"
        )
    return thrust / power


def window_efficiency(
    thrust_per_cycle: NDArray[np.float64],
    power_per_cycle: NDArray[np.float64],
) -> float:
    """The window's efficiency: ``mean(<C_T>_k) / mean(<C_P>_k)``.

    Deliberately NOT ``mean(per_cycle_efficiency(...))``. The two differ whenever the
    per-cycle power varies, and the reported quantity is the ratio of the window's mean
    thrust to its mean power — which is what the experiment measured and what the reference
    row records.
    """
    thrust = np.asarray(thrust_per_cycle, dtype=np.float64)
    power = np.asarray(power_per_cycle, dtype=np.float64)
    if thrust.shape != power.shape or thrust.size == 0:
        raise AlignmentError(
            f"thrust and power cover different cycle counts ({thrust.size} vs {power.size})"
        )
    mean_power = float(np.mean(power))
    if mean_power == 0.0:
        raise AlignmentError("mean cycle power is exactly zero — efficiency is undefined")
    return float(np.mean(thrust)) / mean_power

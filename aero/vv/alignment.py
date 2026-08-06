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
from pydantic import BaseModel, ConfigDict, Field, model_validator

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


#: How far two arms' post-discard origins may sit apart, as a fraction of one period.
#: Not bitwise: the origin is RECOVERED as ``t_start - converged_from_cycle * period``, so a
#: non-zero anchor costs a rounding of order 1e-16 of the period. The bound is still twelve
#: orders tighter than the one time step a dropped row would move the origin by.
_ORIGIN_TOL_CYCLES = 1.0e-9


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
    post_discard_origin: float = Field(
        ...,
        description=(
            "The instant both arms' cycle-0 boundaries sit at -- the first SAMPLE at or "
            "after the discard, which is what `analyse_limit_cycle` segments from. Compared "
            "unconditionally, because index-k pairing means 'the same physical forcing "
            "cycle' only if the two arms count cycles from the same origin."
        ),
    )
    time_base_checked: bool = Field(
        ...,
        description=(
            "Whether the raw sample instants were compared bitwise. NOT a formality: an "
            "AlignedPair is this comparison's evidence, so it must be able to say when the "
            "comparison did not happen rather than looking the same either way."
        ),
    )
    n_samples: int | None = Field(
        default=None,
        ge=2,
        description=(
            "Raw samples on the shared time base -- `None` when no raw times were supplied. "
            "Honest absence rather than a fabricated number (the ADR-025 precedent): the "
            "field previously read 2 in that case, which clears its own floor and reads "
            "like a measurement."
        ),
    )

    @model_validator(mode="after")
    def _a_sample_count_means_the_samples_were_compared(self) -> AlignedPair:
        if (self.n_samples is None) == self.time_base_checked:
            raise ValueError(
                "n_samples and time_base_checked disagree: a sample count is only "
                "meaningful when the two arms' instants were actually compared"
            )
        return self


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

    `baseline_t` / `candidate_t` are the RAW sample times. They stay optional because a
    `LimitCycleAnalysis` does not carry them, but they are now **all-or-nothing**: supplying
    one and not the other used to skip the bitwise comparison entirely while still stamping
    a real-looking `n_samples` on the result, so a pair whose instants were never compared
    was indistinguishable from one that passed. An `AlignedPair` is this function's evidence;
    it has to be able to say what was not checked.

    The **segmentation-anchor** clause needs no raw times at all and is therefore
    unconditional. `LimitCycleAnalysis.t_start` is the settled tail's start, built as
    ``t_kept[0] + converged_from_cycle * period``, so the post-discard origin -- the instant
    cycle 0 begins at -- comes back as ``t_start - converged_from_cycle * period`` from
    fields both arms already carry. Equal `discard_s` does NOT imply equal origins: the
    origin is the first SAMPLE at or after the discard, so one dropped row on one arm moves
    it by a time step and every index-k pair then compares different physical intervals.
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
    if (baseline_t is None) != (candidate_t is None):
        supplied = "baseline_t" if candidate_t is None else "candidate_t"
        raise AlignmentError(
            f"only {supplied} was supplied. The raw-time comparison needs both arms, so a "
            "one-sided call silently skipped it while the returned AlignedPair still looked "
            "checked. Pass both or neither."
        )
    if baseline_t is not None and candidate_t is not None:
        assert_common_time_base(baseline_t, candidate_t)

    # The segmentation anchors, unconditionally. `t_start` is the settled tail's start, so
    # the post-discard origin -- where cycle 0 begins -- is `t_start` minus the whole cycles
    # discarded before it. Equal `discard_s` does not imply equal origins, because the origin
    # is the first SAMPLE at or after the discard.
    origins = tuple(
        arm.t_start - arm.convergence.converged_from_cycle * arm.period
        for arm in (baseline, candidate)
    )
    if abs(origins[0] - origins[1]) > _ORIGIN_TOL_CYCLES * baseline.period:
        raise AlignmentError(
            f"the arms segment from different origins ({origins[0]!r} vs {origins[1]!r}, "
            f"a difference of {abs(origins[0] - origins[1]):.3e} s). Cycle k of one arm is "
            "then a different physical interval from cycle k of the other, and the paired "
            "difference measures the offset rather than the physics. The usual cause is one "
            "arm losing a row -- read_force_history reports n_dropped -- or the two records "
            "not starting at the same instant."
        )

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
    return AlignedPair(
        period=baseline.period,
        pair_start=start,
        n_pairs=end - start,
        baseline_anchor=baseline.convergence.converged_from_cycle,
        candidate_anchor=candidate.convergence.converged_from_cycle,
        post_discard_origin=origins[0],
        time_base_checked=baseline_t is not None,
        n_samples=None if baseline_t is None else int(np.asarray(baseline_t).size),
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

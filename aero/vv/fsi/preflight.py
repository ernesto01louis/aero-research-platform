"""Reusable pre-flight helpers for coupled campaigns — gates S5 (per signal) and I8.

Two pieces, both pure, both consumed by the Stage-20 campaign driver and available to
any future preCICE stage (the session-4 operator decision: I8 is a reusable clause in
``aero/vv/``, not a throwaway spike):

- **Per-signal S5.** ``detect_cycle_convergence`` certifies the FUNDAMENTAL signal only,
  and ``analyse_limit_cycle`` applies the cumulative-drift bound to that same
  fundamental — so a thrust series still drifting under a settled pitch trace would ride
  into a gated mean unexamined (session-7 adversarial review, candidate 14).
  :func:`signal_drift_reports` applies the SAME cumulative bound to every named signal's
  per-cycle series over the settled tail.

- **I8 checkpoint fidelity.** The probe runs the same windows twice — implicit vs
  ``max-iterations 1`` — and compares window-start states. :func:`compare_window_traces`
  is the comparison half: bitwise where the claim is bitwise, with the largest
  discrepancy reported either way, so the ``backward``-vs-``Euler`` decision is measured
  rather than argued.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from aero.postprocess import LimitCycleAnalysis
from aero.postprocess.cycle_detection import cumulative_drift

__all__ = [
    "PreflightError",
    "SignalDriftReport",
    "WindowTraceComparison",
    "compare_window_traces",
    "signal_drift_reports",
]

_STRICT = ConfigDict(extra="forbid", frozen=True)


class PreflightError(Exception):
    """A pre-flight helper was fed something it cannot honestly evaluate."""


class SignalDriftReport(BaseModel):
    """Gate S5 for ONE signal: the cumulative drift bound over the settled tail."""

    model_config = _STRICT

    signal: str
    n_tail_cycles: int = Field(..., ge=1)
    cumulative_mean_drift: float = Field(..., ge=0.0)
    cumulative_amplitude_drift: float = Field(..., ge=0.0)
    tol: float = Field(..., gt=0.0)

    @property
    def passed(self) -> bool:
        return (
            self.cumulative_mean_drift <= self.tol and self.cumulative_amplitude_drift <= self.tol
        )


def signal_drift_reports(
    analysis: LimitCycleAnalysis,
    *,
    signals: tuple[str, ...],
    tol: float = 0.02,
) -> tuple[SignalDriftReport, ...]:
    """S5 per gated signal, from the per-cycle series sliced at the settled anchor.

    ``analysis.cycles`` is anchored at the post-discard origin (deliberately — the
    paired path slices it itself), so the tail is taken from
    ``convergence.converged_from_cycle`` here, the same anchor the fundamental's own
    bound used.
    """
    start = analysis.convergence.converged_from_cycle
    reports: list[SignalDriftReport] = []
    for name in signals:
        if name not in analysis.cycles:
            raise PreflightError(
                f"signal {name!r} is not in the analysis ({sorted(analysis.cycles)}) — "
                "a drift bound over a missing series would silently pass"
            )
        cycles = analysis.cycles[name]
        mean_tail = np.asarray(cycles.per_cycle_mean, dtype=np.float64)[start:]
        amplitude_tail = np.asarray(cycles.per_cycle_amplitude, dtype=np.float64)[start:]
        if mean_tail.size < 2:
            raise PreflightError(
                f"signal {name!r} has {mean_tail.size} settled cycle(s) — a first-to-last "
                "drift needs at least two"
            )
        mean_drift, amplitude_drift = cumulative_drift(mean_tail, amplitude_tail)
        reports.append(
            SignalDriftReport(
                signal=name,
                n_tail_cycles=int(mean_tail.size),
                cumulative_mean_drift=mean_drift,
                cumulative_amplitude_drift=amplitude_drift,
                tol=tol,
            )
        )
    return tuple(reports)


class WindowTraceComparison(BaseModel):
    """I8's comparison half: two runs' window-start traces, compared honestly."""

    model_config = _STRICT

    n_windows: int = Field(..., ge=1)
    bitwise_identical: bool
    max_abs_difference: float = Field(..., ge=0.0)
    where: int = Field(..., ge=0, description="Window index of the largest discrepancy.")


def compare_window_traces(
    reference_t: tuple[float, ...],
    reference_values: tuple[float, ...],
    candidate_t: tuple[float, ...],
    candidate_values: tuple[float, ...],
) -> WindowTraceComparison:
    """Compare two runs' per-window traces on an identical schedule.

    The schedules must agree BITWISE — both runs write the same prescribed windows, and
    a shifted schedule would make the value comparison meaningless — but the VALUES are
    compared with the discrepancy reported, because "how far apart" is the measurement
    I8 exists to make.
    """
    if len(reference_t) != len(candidate_t) or len(reference_t) < 1:
        raise PreflightError(
            f"the two runs wrote {len(reference_t)} and {len(candidate_t)} windows — "
            "the probe must compare the SAME windows"
        )
    if tuple(reference_t) != tuple(candidate_t):
        raise PreflightError(
            "the two runs' window schedules differ — bitwise-equal times are the "
            "precondition for comparing states at all"
        )
    if len(reference_values) != len(reference_t) or len(candidate_values) != len(candidate_t):
        raise PreflightError("a trace's values and times differ in length")
    reference = np.asarray(reference_values, dtype=np.float64)
    candidate = np.asarray(candidate_values, dtype=np.float64)
    differences = np.abs(reference - candidate)
    worst = int(np.argmax(differences))
    return WindowTraceComparison(
        n_windows=len(reference_t),
        bitwise_identical=bool((reference == candidate).all()),
        max_abs_difference=float(differences[worst]),
        where=worst,
    )

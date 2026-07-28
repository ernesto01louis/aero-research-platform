"""Limit-cycle statistics over a DERIVED analysis window (Stage 19; additive to ADR-019).

Given several signals sampled on a common time base, this decides — by rule, not by
hand — which part of the record is an established limit cycle, and reports each signal's
mean, amplitude and frequency over exactly that window.

Three properties are the point of the module:

**One period for every signal.** The period is taken from a nominated *fundamental*
signal and applied to all of them. Higher harmonics segmented at their own dominant
frequency produce per-cycle amplitudes that alternate between half-strokes, which trips
the cycle-convergence drift check even on a perfectly periodic record — measured on the
published Turek-Hron FSI3 reference itself: amplitude drift 0.070 for the streamwise tip
displacement and 0.163 for drag, against a 0.02 tolerance, on data that is by
construction a converged limit cycle.

**The window is computed, not chosen.** An unconditional discard removes the start-up
transient, then :func:`aero.postprocess.detect_cycle_convergence` finds the longest
settled tail, and the analysis window is exactly that tail. Two people analysing the same
record get the same answer, and "run a bit longer until it passes" is not available.

**Not converged is an error, not a number.** If the settled tail is shorter than the
caller's minimum, this raises. A displacement amplitude read off a drifting record is not
a measurement of a limit cycle, however close to a published value it happens to land.

**Consecutive drift is not enough.** :func:`aero.postprocess.detect_cycle_convergence`
compares *adjacent* cycles, so a record that grows steadily but slowly satisfies it
without bound: at 1.2 % per cycle every adjacent difference is inside a 2 % tolerance
while the amplitude grows 30 % across the window. That is not a pathological signal, it
is what a slowly saturating added-mass instability looks like — the realistic FSI3
failure mode. A CUMULATIVE linear-trend bound over the settled tail is therefore applied
as well. On the published Turek-Hron FSI3 reference the cumulative amplitude trend drift is
0.14 % over seven cycles, so the bound accepts genuine data with two orders of magnitude
to spare while refusing steady growth.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
from pydantic import BaseModel, Field, model_validator

from aero.postprocess._base import _STRICT, Signal
from aero.postprocess.cycle_detection import (
    CycleConvergenceReport,
    cumulative_drift,
    detect_cycle_convergence,
)
from aero.postprocess.frequency import dominant_frequency
from aero.postprocess.phase_averaging import segment_cycles


class LimitCycleError(RuntimeError):
    """The record does not contain an analysable limit cycle."""


class SignalStatistics(BaseModel):
    """One signal's statistics over the analysis window."""

    model_config = _STRICT

    name: str = Field(..., min_length=1)
    mean: float = Field(..., description="Mean over full cycles of the per-cycle mean.")
    amplitude: float = Field(
        ..., ge=0.0, description="Mean over full cycles of the per-cycle half peak-to-peak."
    )
    frequency: float = Field(..., gt=0.0, description="This signal's own dominant frequency [Hz].")
    minimum: float
    maximum: float
    n_cycles: int = Field(..., ge=1)


class LimitCycleAnalysis(BaseModel):
    """The derived analysis window and every signal's statistics over it."""

    model_config = _STRICT

    fundamental: str = Field(..., min_length=1)
    fundamental_frequency: float = Field(..., gt=0.0)
    period: float = Field(..., gt=0.0)
    discard_s: float = Field(..., ge=0.0, description="Unconditional start-up discard.")
    t_start: float = Field(..., description="First instant of the analysis window.")
    t_end: float = Field(..., description="Last instant of the record.")
    n_cycles_after_discard: int = Field(..., ge=1)
    n_settled_cycles: int = Field(..., ge=1, description="Length of the settled tail (the window).")
    mean_drift: float = Field(..., ge=0.0, description="Worst ADJACENT-cycle relative drift.")
    amplitude_drift: float = Field(..., ge=0.0, description="Worst adjacent-cycle drift.")
    cumulative_mean_drift: float = Field(
        ..., ge=0.0, description="Linear-trend total change of the per-cycle mean over the window."
    )
    cumulative_amplitude_drift: float = Field(
        ...,
        ge=0.0,
        description="Linear-trend total change of the per-cycle amplitude over the window.",
    )
    statistics: dict[str, SignalStatistics] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _fundamental_present(self) -> LimitCycleAnalysis:
        if self.fundamental not in self.statistics:
            raise ValueError(f"fundamental signal {self.fundamental!r} missing from the statistics")
        return self

    def of(self, name: str) -> SignalStatistics:
        try:
            return self.statistics[name]
        except KeyError:
            raise LimitCycleError(
                f"no signal {name!r} in the analysis (have: {', '.join(sorted(self.statistics))})"
            ) from None

    @property
    def window_duration(self) -> float:
        return self.t_end - self.t_start


def analyse_limit_cycle(
    t: np.ndarray,
    signals: Mapping[str, np.ndarray],
    *,
    fundamental: str,
    discard_s: float = 0.0,
    min_cycles: int = 4,
    mean_drift_tol: float = 0.01,
    amplitude_drift_tol: float = 0.02,
    cumulative_drift_tol: float = 0.02,
) -> LimitCycleAnalysis:
    """Analyse a multi-signal record over the settled tail of its limit cycle.

    Raises :class:`LimitCycleError` unless at least `min_cycles` settled cycles remain
    after `discard_s`. The caller pre-registers `discard_s` and `min_cycles`; this
    function never adjusts them to make a record pass.
    """
    if fundamental not in signals:
        raise LimitCycleError(f"fundamental signal {fundamental!r} not among {sorted(signals)}")
    t = np.asarray(t, dtype=np.float64)
    if t.size < 2:
        raise LimitCycleError("fewer than two samples — nothing to analyse")

    # `discard_s` is an ABSOLUTE instant on the solver clock, not an offset from the
    # first sample: the pre-registered rule is "the first N seconds of physical time are
    # not a limit cycle", which stays the same statement whether the record starts at
    # t = 0 (our solve) or at t = 5 s (the published reference series).
    keep = t >= discard_s
    if not bool(keep.any()):
        raise LimitCycleError(
            f"discarding t < {discard_s:g} s leaves no samples "
            f"(record spans [{t[0]:g}, {t[-1]:g}] s) — the run has not passed the "
            "start-up transient"
        )
    t_kept = t[keep]
    kept = {name: np.asarray(values, dtype=np.float64)[keep] for name, values in signals.items()}

    fundamental_signal = Signal.from_arrays(t_kept, kept[fundamental], name=fundamental)
    estimate = dominant_frequency(fundamental_signal)
    period = 1.0 / estimate.frequency

    try:
        samples = segment_cycles(fundamental_signal, period=period)
    except ValueError as exc:
        raise LimitCycleError(
            f"cannot segment {fundamental!r} into cycles of {period:g} s "
            f"over [{t_kept[0]:g}, {t_kept[-1]:g}] s — {exc}"
        ) from exc

    convergence: CycleConvergenceReport = detect_cycle_convergence(
        samples, mean_drift_tol=mean_drift_tol, amplitude_drift_tol=amplitude_drift_tol
    )
    if not convergence.converged or convergence.n_converged_cycles < min_cycles:
        raise LimitCycleError(
            f"no periodic steady state: {convergence.n_converged_cycles} settled cycle(s) of "
            f"{convergence.n_cycles} after discarding t < {discard_s:g} s "
            f"(need {min_cycles}; mean drift {convergence.mean_drift:.3f} vs "
            f"{convergence.mean_drift_tol:.3f}, amplitude drift "
            f"{convergence.amplitude_drift:.3f} vs {convergence.amplitude_drift_tol:.3f}). "
            "A quantity measured on a drifting record is not a limit-cycle measurement — "
            "run longer or investigate; do not widen the window."
        )

    # The analysis window IS the settled tail — derived from the rule, never selected.
    t_start = float(t_kept[0]) + convergence.converged_from_cycle * period
    window = t_kept >= t_start - 1.0e-12
    t_window = t_kept[window]

    statistics: dict[str, SignalStatistics] = {}
    tail = segment_cycles(
        Signal.from_arrays(t_window, kept[fundamental][window], name=fundamental), period=period
    )
    # The detector counts cycles on a segmentation anchored at t_kept[0]; the statistics
    # are computed on a re-segmentation anchored at t_start. Those can differ by one, so
    # report the number of cycles actually averaged into the gated numbers, not the
    # detector's — a settled-cycle count that overstates the evidence is a small lie in a
    # provenance-bearing field.
    if tail.n_cycles < min_cycles:
        raise LimitCycleError(
            f"the settled tail re-segments into {tail.n_cycles} full cycle(s), fewer than "
            f"the required {min_cycles}, even though the detector counted "
            f"{convergence.n_converged_cycles}. The gated statistics would average fewer "
            "cycles than the pre-registered minimum."
        )
    cumulative_mean_drift, cumulative_amplitude_drift = cumulative_drift(
        np.asarray(tail.per_cycle_mean), np.asarray(tail.per_cycle_amplitude)
    )
    if max(cumulative_mean_drift, cumulative_amplitude_drift) > cumulative_drift_tol:
        raise LimitCycleError(
            f"the settled tail drifts monotonically: over its {tail.n_cycles} cycles the "
            f"per-cycle mean changes {cumulative_mean_drift:.1%} and the amplitude "
            f"{cumulative_amplitude_drift:.1%} from first to last (bound "
            f"{cumulative_drift_tol:.1%}). Consecutive-cycle drift stayed inside "
            f"{mean_drift_tol:.1%}/{amplitude_drift_tol:.1%}, which is exactly how a slowly "
            "growing record masquerades as a limit cycle — the quantity is still moving. "
            "Run longer, or investigate the coupling; do not widen the bound."
        )
    for name, values in kept.items():
        series = values[window]
        signal = Signal.from_arrays(t_window, series, name=name)
        cycles = segment_cycles(signal, period=period)
        statistics[name] = SignalStatistics(
            name=name,
            mean=float(np.mean(cycles.per_cycle_mean)),
            amplitude=float(np.mean(cycles.per_cycle_amplitude)),
            frequency=dominant_frequency(signal).frequency,
            minimum=float(series.min()),
            maximum=float(series.max()),
            n_cycles=cycles.n_cycles,
        )

    return LimitCycleAnalysis(
        fundamental=fundamental,
        fundamental_frequency=estimate.frequency,
        period=period,
        discard_s=discard_s,
        t_start=t_start,
        t_end=float(t_kept[-1]),
        n_cycles_after_discard=samples.n_cycles,
        n_settled_cycles=tail.n_cycles,
        mean_drift=convergence.mean_drift,
        amplitude_drift=convergence.amplitude_drift,
        cumulative_mean_drift=cumulative_mean_drift,
        cumulative_amplitude_drift=cumulative_amplitude_drift,
        statistics=statistics,
    )

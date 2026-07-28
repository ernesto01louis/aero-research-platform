"""Periodic-steady-state (cycle-convergence) detection.

A reported unsteady quantity must come from a **converged limit cycle**, not a
transient — the Stage-11 GO gate and the precondition for Stage 12's statistical
uncertainty (batch-means over the converged tail). This module inspects the
per-cycle samples (:class:`~aero.postprocess.phase_averaging.CycleSamples`) and
decides, fail-loud, whether the cycle-to-cycle mean and amplitude have settled.

The normalisation is robust to a **zero-mean oscillation** (e.g. the lift of a
symmetric shedding cylinder, whose per-cycle mean is ~0): when the mean magnitude is
negligible against the oscillation amplitude, mean drift is normalised by the
amplitude scale instead of by the (near-zero) mean — otherwise a tiny absolute mean
wobble would divide by ~0 and spuriously read as huge drift.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, Field

from aero.postprocess._base import _STRICT
from aero.postprocess.phase_averaging import CycleSamples

_EPS = 1.0e-30


class CycleConvergenceReport(BaseModel):
    """Whether the limit cycle has converged, and how much of the tail is usable."""

    model_config = _STRICT

    converged: bool = Field(..., description="True iff a settled tail of cycles was found.")
    n_cycles: int = Field(..., ge=1, description="Total cycles analysed.")
    n_converged_cycles: int = Field(
        ..., ge=0, description="Length of the settled tail (batch-means samples for Stage 12)."
    )
    converged_from_cycle: int = Field(
        ..., ge=0, description="Index of the first cycle in the settled tail (== n_cycles if none)."
    )
    mean_drift: float = Field(
        ...,
        ge=0.0,
        description="Max consecutive relative drift of the per-cycle mean over the tail.",
    )
    amplitude_drift: float = Field(
        ..., ge=0.0, description="Max consecutive relative drift of the per-cycle amplitude."
    )
    mean_drift_tol: float = Field(..., gt=0.0)
    amplitude_drift_tol: float = Field(..., gt=0.0)
    # Cumulative (linear-trend) drift over the settled tail. Always computed (cheap,
    # diagnostic); only factored into `converged` when the caller passes a cumulative
    # tolerance (see detect_cycle_convergence). Defaulted so pre-existing direct
    # constructions of this model remain valid.
    cumulative_mean_drift: float = Field(
        default=0.0,
        ge=0.0,
        description="Linear-trend total change of the per-cycle mean over the tail.",
    )
    cumulative_amplitude_drift: float = Field(
        default=0.0,
        ge=0.0,
        description="Linear-trend total change of the per-cycle amplitude over the tail.",
    )
    cumulative_mean_drift_tol: float | None = Field(
        default=None, description="Cumulative bound applied, or None if not gated on."
    )
    cumulative_amplitude_drift_tol: float | None = Field(
        default=None, description="Cumulative bound applied, or None if not gated on."
    )


def _trend_drift(series: np.ndarray, *, scale: float) -> float:
    """The total relative change a least-squares LINEAR TREND predicts across the series.

    Deliberately a trend, not a first-to-last or block-means difference. A limit cycle can
    *beat* — its per-cycle amplitude wobbles a few percent around a stationary level
    (imperfect lock-in, harmonic interaction) — and any endpoint-based measure then reads
    the beat's phase rather than any drift, flipping a genuine converged cycle to
    "drifting". A least-squares slope averages the beat out: a stationary wobble has zero
    slope, a slowly growing record has a clear one. Empirically decisive — over 107
    historical moving-mesh runs the trend drift is 1e-4 (zero flips), while the
    monotonically growing FSI3 test record reads 0.22 and the published FSI3 reference
    reads 1.4e-3.
    """
    s = np.asarray(series, dtype=np.float64)
    n = s.size
    if n < 3:
        return 0.0
    slope = float(np.polyfit(np.arange(n), s, 1)[0])
    return abs(slope * (n - 1)) / scale


def cumulative_drift(mean: np.ndarray, amplitude: np.ndarray) -> tuple[float, float]:
    """Trend drift of a per-cycle mean and amplitude series over the settled tail.

    The single shared implementation, called both by :func:`detect_cycle_convergence`
    (Stage 11) and by :mod:`aero.postprocess.limit_cycle` (Stage 19), so the two gates
    cannot drift apart. Uses a least-squares linear trend (see :func:`_trend_drift`), which
    a stationary but beating limit cycle passes and a slowly growing one fails. Normalised
    like the adjacent-cycle drifts: amplitude by its own magnitude, a near-zero mean by the
    oscillation amplitude instead of by itself, so the bounds are commensurable.
    """
    m = np.asarray(mean, dtype=np.float64)
    a = np.asarray(amplitude, dtype=np.float64)
    if m.size < 2:
        return 0.0, 0.0
    amp_scale = max(float(np.max(np.abs(a))), _EPS)
    mean_mag = float(np.mean(np.abs(m)))
    mean_scale = max(mean_mag if mean_mag >= 0.05 * amp_scale else amp_scale, _EPS)
    return (
        _trend_drift(m, scale=mean_scale),
        _trend_drift(a, scale=amp_scale),
    )


def detect_cycle_convergence(
    samples: CycleSamples,
    *,
    window: int = 3,
    mean_drift_tol: float = 0.01,
    amplitude_drift_tol: float = 0.02,
    cumulative_mean_drift_tol: float | None = None,
    cumulative_amplitude_drift_tol: float | None = None,
) -> CycleConvergenceReport:
    """Find the longest settled tail of cycles and judge convergence.

    Scanning backward from the last cycle, extend the settled tail while both the
    consecutive per-cycle mean drift and amplitude drift stay within tolerance. The
    cycle is ``converged`` iff the settled tail is at least ``window + 1`` cycles long
    (enough for a meaningful batch-means estimate). ``mean_drift`` / ``amplitude_drift``
    report the worst consecutive drift over the settled tail (or over the whole record
    when nothing settled).

    **Cumulative bound (opt-in).** Consecutive-cycle drift alone certifies a record that
    grows steadily but slowly: at 1.2 % per cycle every adjacent difference sits inside a
    2 % tolerance while the amplitude grows 30 % across the window — a slowly saturating
    instability wearing a limit cycle's clothes (found by adversarial review of the
    Stage-19 gate, which this same function backs). When
    ``cumulative_mean_drift_tol`` / ``cumulative_amplitude_drift_tol`` are given, the
    linear-trend drift over the settled tail must also stay within them for ``converged``
    to be true. The cumulative drifts are **always** computed and reported; passing the
    tolerances is what makes them *gate*. Default ``None`` preserves the pre-review
    behaviour byte-for-byte, so no historical verdict changes unless a caller opts in.
    """
    m = np.asarray(samples.per_cycle_mean, dtype=np.float64)
    a = np.asarray(samples.per_cycle_amplitude, dtype=np.float64)
    n = samples.n_cycles
    min_tail = window + 1

    # Normalisation scales. Amplitude by its own (positive) magnitude; mean by its own
    # magnitude when significant, else by the oscillation amplitude (zero-mean case).
    amp_scale = float(np.max(np.abs(a))) if n else 0.0
    amp_scale = max(amp_scale, _EPS)
    mean_mag = float(np.mean(np.abs(m))) if n else 0.0
    mean_scale = mean_mag if mean_mag >= 0.05 * amp_scale else amp_scale
    mean_scale = max(mean_scale, _EPS)

    if n < 2:
        # A single cycle cannot exhibit cycle-to-cycle drift; not enough to converge.
        return CycleConvergenceReport(
            converged=False,
            n_cycles=n,
            n_converged_cycles=0,
            converged_from_cycle=n,
            mean_drift=0.0,
            amplitude_drift=0.0,
            mean_drift_tol=mean_drift_tol,
            amplitude_drift_tol=amplitude_drift_tol,
        )

    d_mean = np.abs(np.diff(m)) / mean_scale  # length n-1, gap i is between cycle i and i+1
    d_amp = np.abs(np.diff(a)) / amp_scale
    ok = (d_mean <= mean_drift_tol) & (d_amp <= amplitude_drift_tol)

    # Extend the settled tail backward from the last cycle.
    c = n - 1
    while c - 1 >= 0 and bool(ok[c - 1]):
        c -= 1
    n_tail = n - c
    converged = n_tail >= min_tail

    if n_tail >= 2:
        tail_mean_drift = float(np.max(d_mean[c:]))
        tail_amp_drift = float(np.max(d_amp[c:]))
    else:
        # Nothing settled beyond the last cycle — report the worst drift overall so the
        # diagnostic is informative rather than trivially zero.
        tail_mean_drift = float(np.max(d_mean))
        tail_amp_drift = float(np.max(d_amp))

    # Cumulative drift over whatever tail we settled on (or the whole record if none).
    tail_slice = slice(c, None) if n_tail >= 2 else slice(None)
    cum_mean, cum_amp = cumulative_drift(m[tail_slice], a[tail_slice])
    if converged and cumulative_mean_drift_tol is not None:
        converged = converged and cum_mean <= cumulative_mean_drift_tol
    if converged and cumulative_amplitude_drift_tol is not None:
        converged = converged and cum_amp <= cumulative_amplitude_drift_tol

    return CycleConvergenceReport(
        converged=converged,
        n_cycles=n,
        n_converged_cycles=n_tail if converged else 0,
        converged_from_cycle=c if converged else n,
        mean_drift=tail_mean_drift,
        amplitude_drift=tail_amp_drift,
        mean_drift_tol=mean_drift_tol,
        amplitude_drift_tol=amplitude_drift_tol,
        cumulative_mean_drift=cum_mean,
        cumulative_amplitude_drift=cum_amp,
        cumulative_mean_drift_tol=cumulative_mean_drift_tol,
        cumulative_amplitude_drift_tol=cumulative_amplitude_drift_tol,
    )

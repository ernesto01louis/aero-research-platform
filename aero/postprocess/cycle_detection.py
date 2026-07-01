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


def detect_cycle_convergence(
    samples: CycleSamples,
    *,
    window: int = 3,
    mean_drift_tol: float = 0.01,
    amplitude_drift_tol: float = 0.02,
) -> CycleConvergenceReport:
    """Find the longest settled tail of cycles and judge convergence.

    Scanning backward from the last cycle, extend the settled tail while both the
    consecutive per-cycle mean drift and amplitude drift stay within tolerance. The
    cycle is ``converged`` iff the settled tail is at least ``window + 1`` cycles long
    (enough for a meaningful batch-means estimate). ``mean_drift`` / ``amplitude_drift``
    report the worst consecutive drift over the settled tail (or over the whole record
    when nothing settled).
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

    return CycleConvergenceReport(
        converged=converged,
        n_cycles=n,
        n_converged_cycles=n_tail if converged else 0,
        converged_from_cycle=c if converged else n,
        mean_drift=tail_mean_drift,
        amplitude_drift=tail_amp_drift,
        mean_drift_tol=mean_drift_tol,
        amplitude_drift_tol=amplitude_drift_tol,
    )

"""Statistical (sampling) uncertainty of a time/phase-averaged quantity — ``u95_statistical``.

CONSTITUTION Invariant 10 (IMPROVEMENT-EXCEEDS-UNCERTAINTY) requires the total 95 %
uncertainty of a reported quantity to compose three independent contributions,

    U95 = sqrt( u95_numerical**2 + u95_statistical**2 + u95_input**2 )

where ``u95_numerical`` is the discretization uncertainty (GCI / ASME V&V 20; covers *only*
this) and ``u95_statistical`` is the sampling error of a **time- or phase-average** — the term
GCI cannot see, and the reason a non-steady thesis-grade quantity with ``u95_statistical == 0``
is rejected by :class:`aero.vv.reportable.ReportableResult`. This module computes it.

The input is the converged per-cycle-mean tail exposed by Stage 11:
``samples.per_cycle_mean[report.converged_from_cycle:]`` (a
:class:`~aero.postprocess.phase_averaging.CycleSamples` restricted to the settled tail
reported by :func:`aero.postprocess.cycle_detection.detect_cycle_convergence`). Those
per-cycle means are cycle-to-cycle **correlated**, so a naive ``sigma / sqrt(N)`` under-states
the error.

**Method.** Non-overlapping batch means (NOBM) is the primary estimator, with the integrated
autocorrelation time (Sokal automatic windowing) → effective sample size ``N_eff`` as an
independent cross-check. NOBM is assumption-light on a coarse per-cycle series and yields an
honest small-sample degrees-of-freedom for the Student-t half-width; ``tau_int`` independently
quantifies the correlation and yields ``N_eff``. The estimator **trusts
:func:`aero.postprocess.cycle_detection.detect_cycle_convergence` for stationarity** (that is its
precondition) and hard-RAISES only when the tail cannot support any estimate — the run is not
converged, there are too few converged cycles (``N < min_samples``), or the signal is dead
(variation below float precision) — the Stage-12 NO-GO ("STOP and investigate cycle-convergence,
not the estimator"). "``N_eff`` too small" (a too-autocorrelated tail) and NOBM/``tau_int``
disagreement clear the soft ``reliable`` flag rather than raising: the estimator still returns an
honest (wide) number, and the thesis-grade composer is where an unreliable term is refused a
``thesis-grade`` tag. References: ASME V&V 20-2009 §7; Roy & Oberkampf (2011) CMAME 200; Fishman
(1978) / Schmeiser (1982) batch means; Sokal (1997) automatic windowing.

Strict pydantic, frozen, ``extra="forbid"``. PLATFORM-NOT-HUB: stdlib + numpy + pydantic only.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from aero.postprocess.cycle_detection import CycleConvergenceReport
from aero.postprocess.phase_averaging import CycleSamples

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_default=True,
)

_EPS = 1.0e-30
_CONFIDENCE = 0.95  # two-sided; the half-width uses the 0.975 Student-t quantile.

# Estimator knobs.
DEFAULT_MIN_SAMPLES = 8  # fewer converged cycles cannot yield >= 4 batches of >= 2 cycles.
MIN_BATCHES = 4
MAX_BATCHES = 8  # cap so batches stay long enough to decorrelate (the sqrt(N) rule, bounded).
# `reliable` requires BOTH NOBM/tau_int agreement AND enough effective samples: an autocorrelation
# so strong that N_eff falls below the raw-N floor means the run should be extended, not reported.
N_EFF_RELIABLE_MIN = 8.0
_DEAD_REL_TOL = 1.0e-12  # std <= this * scale -> effectively constant (dead signal), a hard NO-GO.
# NOBM / tau_int agreement band (ratio = u95_nobm / u95_tau) -> part of the soft `reliable` flag.
_CROSSCHECK_LO = 0.5
_CROSSCHECK_HI = 2.0
_SOKAL_C = 6.0  # automatic-windowing constant: stop when window k >= c * tau.

# 0.975 quantile of Student's t by degrees of freedom (two-sided 95 % interval). The reachable
# df here is small and bounded (NOBM df = n_batches - 1 in [3, 7]); a committed table is exact
# and keeps this module scipy-free (PLATFORM-NOT-HUB). Lookups between tabulated df round DOWN
# to the nearest tabulated df (larger t -> wider interval -> conservative).
_T_975: dict[int, float] = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
    40: 2.021,
    50: 2.009,
    60: 2.000,
    80: 1.990,
    100: 1.984,
}


class StatisticalUncertaintyError(ValueError):
    """The batch-means estimator cannot produce a stable ``u95_statistical``.

    Per the Stage-12 GO/NO-GO: STOP and investigate the cycle-convergence, not the estimator.
    A ``ValueError`` subclass so a failure inside a pydantic model surfaces as a
    ``ValidationError`` — fail-loud, never a silent zero (mirrors
    :class:`aero.vv.reportable.SmallSignalError`).
    """


def _student_t_975(dof: int) -> float:
    """0.975 Student-t quantile for ``dof`` degrees of freedom (conservative between rows)."""
    if dof < 1:
        raise StatisticalUncertaintyError(f"degrees of freedom must be >= 1, got {dof}")
    if dof in _T_975:
        return _T_975[dof]
    below = [d for d in _T_975 if d <= dof]
    # dof >= 1 guarantees a tabulated row at or below it; round DOWN (wider, conservative).
    return _T_975[max(below)]


def integrated_autocorr_time(values: Sequence[float]) -> float:
    """Integrated autocorrelation time ``tau_int`` via Sokal automatic windowing.

    ``tau_int = 0.5 + sum_{k>=1} rho_k`` truncated at the first window ``k >= c * tau_int``
    (``c = 6``); floored at 0.5 (the IID limit, for which ``N_eff = N / (2*tau_int) = N``).
    """
    x = np.asarray(values, dtype=np.float64)
    x = x - x.mean()
    n = x.size
    denom = float(x @ x)
    if denom <= 0.0:
        return 0.5
    acf = np.correlate(x, x, mode="full")[n - 1 :] / denom  # rho_0 .. rho_{n-1}, rho_0 = 1
    tau = 0.5
    for k in range(1, n):
        tau += float(acf[k])
        if k >= _SOKAL_C * tau:
            break
    return max(tau, 0.5)


class StatisticalUncertainty(BaseModel):
    """The sampling ``u95_statistical`` of a time/phase-average, with its NOBM + tau_int diagnostics.

    ``u95_statistical`` is an **absolute** half-width in the value's own units (so it
    root-sum-squares cleanly with the other U95 terms); ``rel_half_width`` is a diagnostic
    fraction. ``reliable`` is a soft flag (NOBM/tau_int agreement AND ``N_eff`` above the
    reliability floor); an unreliable term is still returned (honest, wide) — the thesis-grade
    composer is where it is refused a publication tag.
    """

    model_config = _STRICT

    method: Literal["nobm"] = Field(default="nobm", description="Primary estimator used.")
    n_samples: int = Field(..., ge=1, description="Number of converged-cycle samples.")
    mean: float = Field(..., description="Mean of the converged-cycle samples.")
    std: float = Field(..., ge=0.0, description="Sample std (ddof=1) of the tail.")
    n_batches: int = Field(..., ge=1, description="Non-overlapping batches.")
    batch_size: int = Field(
        ..., ge=1, description="Cycles per batch (remainder dropped from front)."
    )
    dof: int = Field(..., ge=1, description="Student-t degrees of freedom (n_batches - 1).")
    t_quantile: float = Field(..., gt=0.0, description="0.975 Student-t quantile at dof.")
    se: float = Field(..., ge=0.0, description="Standard error of the mean (batch means).")
    u95_statistical: float = Field(
        ..., ge=0.0, description="95 % half-width, absolute (value units) = t_quantile * se."
    )
    rel_half_width: float = Field(..., ge=0.0, description="u95_statistical / scale (diagnostic).")
    autocorr_time: float = Field(
        ..., ge=0.0, description="Integrated autocorrelation time tau_int."
    )
    n_eff: float = Field(..., gt=0.0, description="Effective sample size N / (2*tau_int).")
    crosscheck_ratio: float = Field(
        ..., gt=0.0, description="u95_nobm / u95_tau (NOBM vs autocorrelation cross-check)."
    )
    reliable: bool = Field(
        ...,
        description="True iff crosscheck_ratio is in [0.5, 2.0] AND n_eff >= the reliability floor. "
        "A soft flag: an unreliable term is still honest (wide) — extend the run to tighten it.",
    )


def statistical_uncertainty_from_samples(
    values: Sequence[float],
    *,
    amp_scale: float | None = None,
    converged: bool = True,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> StatisticalUncertainty:
    """Compute ``u95_statistical`` from a converged per-cycle-mean tail (NOBM + tau_int).

    ``amp_scale`` (the oscillation amplitude) is used only to normalise ``rel_half_width`` for a
    near-zero-mean quantity (the zero-mean guard from ``cycle_detection``); the returned
    ``u95_statistical`` is always absolute. RAISES :class:`StatisticalUncertaintyError` when the
    tail is not a trustworthy stationary limit cycle (see module docstring).
    """
    if not converged:
        raise StatisticalUncertaintyError(
            "no converged tail: the limit cycle has not converged. Run more cycles and "
            "investigate cycle-convergence, not the estimator."
        )
    x = np.asarray(values, dtype=np.float64)
    n = x.size
    if n < min_samples:
        raise StatisticalUncertaintyError(
            f"only N={n} converged cycles (< {min_samples}); too few for a stable batch-means "
            "u95_statistical. Extend the run to accumulate more converged cycles."
        )
    mean = float(x.mean())
    std = float(x.std(ddof=1))
    amp = float(amp_scale) if amp_scale is not None else 0.0
    # Dead-signal guard is RELATIVE: an all-equal tail still has std ~ 1e-16 in float64, so a bare
    # `std == 0` would miss it and the autocorrelation of that float noise would spuriously fire.
    if std <= _DEAD_REL_TOL * max(abs(mean), amp, _EPS):
        raise StatisticalUncertaintyError(
            "converged-cycle values are effectively constant (variation below float precision) — "
            "not a real limit cycle; investigate cycle-convergence / the signal, not the estimator."
        )

    # --- Non-overlapping batch means (primary) ------------------------------------------------
    n_batches = min(max(MIN_BATCHES, math.floor(math.sqrt(n))), MAX_BATCHES)
    batch_size = n // n_batches
    used = x[n - n_batches * batch_size :]  # drop the remainder from the FRONT (transient-adjacent)
    batch_means = used.reshape(n_batches, batch_size).mean(axis=1)
    s_batch = float(batch_means.std(ddof=1))
    se = s_batch / math.sqrt(n_batches)
    dof = n_batches - 1
    t = _student_t_975(dof)
    u95 = t * se

    # --- Integrated autocorrelation time -> N_eff (independent cross-check) --------------------
    tau = integrated_autocorr_time(values)
    n_eff = max(n / (2.0 * tau), 1.0)
    dof_tau = max(round(n_eff) - 1, 1)
    u95_tau = _student_t_975(dof_tau) * (std / math.sqrt(n_eff))
    ratio = u95 / u95_tau if u95_tau > 0.0 else math.inf
    # `reliable` is a SOFT flag (the thesis-grade composer decides what to do with it), not a hard
    # raise: NOBM's few-batch s_batch is itself noisy, so a mismatch warns rather than fatally stops.
    # It requires both estimators to agree AND enough effective samples ("N_eff too small" -> unreliable).
    reliable = (_CROSSCHECK_LO <= ratio <= _CROSSCHECK_HI) and (n_eff >= N_EFF_RELIABLE_MIN)

    # rel_half_width: normalise by the mean magnitude, or by the amplitude for a zero-mean
    # oscillation (the cycle_detection guard) — a diagnostic only; u95_statistical stays absolute.
    mean_mag = abs(mean)
    scale = mean_mag if mean_mag >= 0.05 * amp else amp
    scale = max(scale, _EPS)

    return StatisticalUncertainty(
        n_samples=n,
        mean=mean,
        std=std,
        n_batches=n_batches,
        batch_size=batch_size,
        dof=dof,
        t_quantile=t,
        se=se,
        u95_statistical=u95,
        rel_half_width=u95 / scale,
        autocorr_time=tau,
        n_eff=n_eff,
        crosscheck_ratio=float(ratio),
        reliable=reliable,
    )


def statistical_uncertainty(
    samples: CycleSamples,
    report: CycleConvergenceReport,
    *,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> StatisticalUncertainty:
    """Compute ``u95_statistical`` over the converged tail of a moving-case ``CycleSamples``.

    Slices ``per_cycle_mean[report.converged_from_cycle:]`` (the Stage-11 batch-means seam) and
    derives the amplitude scale from the same tail. RAISES if the report is not converged.
    """
    start = report.converged_from_cycle
    tail = samples.per_cycle_mean[start:]
    amp_tail = samples.per_cycle_amplitude[start:]
    amp_scale = float(np.max(np.abs(np.asarray(amp_tail, dtype=np.float64)))) if amp_tail else 0.0
    return statistical_uncertainty_from_samples(
        tail,
        amp_scale=amp_scale,
        converged=report.converged,
        min_samples=min_samples,
    )

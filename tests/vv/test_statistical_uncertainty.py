"""Batch-means statistical uncertainty (``u95_statistical``) — Stage 12 estimator tests.

Pure-host, hermetic (synthetic signals + a fixed seed): the IID limit, an injected AR(1)
correlation, the fail-loud NO-GO paths, and the ``CycleSamples`` wrapper over the Stage-11
seam. No cluster needed — this suite backs the required ``small-signal-gate`` CI job.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from aero.postprocess.cycle_detection import detect_cycle_convergence
from aero.postprocess.phase_averaging import CycleSamples
from aero.vv.statistical_uncertainty import (
    N_EFF_RELIABLE_MIN,
    StatisticalUncertaintyError,
    _student_t_975,
    integrated_autocorr_time,
    statistical_uncertainty,
    statistical_uncertainty_from_samples,
)


def test_iid_recovers_sigma_over_sqrt_n() -> None:
    """For an IID sample the batch-means half-width ~= 1.96 sigma/sqrt(N) and N_eff ~= N."""
    rng = np.random.default_rng(0)
    sigma, n = 0.3, 200
    x = rng.normal(5.0, sigma, n)
    su = statistical_uncertainty_from_samples(x, amp_scale=sigma)
    naive = 1.96 * sigma / math.sqrt(n)
    assert su.method == "nobm"
    assert su.reliable
    assert su.u95_statistical > 0.0
    assert 0.5 * naive <= su.u95_statistical <= 2.0 * naive
    assert su.n_eff > 0.4 * n  # IID -> tau_int ~ 0.5 -> N_eff ~ N (allowing estimator noise)


def test_ar1_correlation_reduces_n_eff() -> None:
    """An injected AR(1) correlation must drop N_eff below N (the whole point of the term)."""
    rng = np.random.default_rng(1)
    phi, n = 0.6, 400
    e = rng.normal(0.0, 1.0, n)
    y = np.zeros(n)
    for i in range(1, n):
        y[i] = phi * y[i - 1] + e[i]
    su = statistical_uncertainty_from_samples(y, amp_scale=1.0)
    # Analytic ESS for AR(1) is N*(1-phi)/(1+phi) = N/4; the biased sample estimator lands lower.
    assert su.n_eff < 0.7 * n
    assert su.u95_statistical > 0.0


def test_dead_signal_raises() -> None:
    """An all-equal tail (std ~ 1e-16 in float64, not exactly 0) must be caught as dead."""
    with pytest.raises(StatisticalUncertaintyError, match="constant"):
        statistical_uncertainty_from_samples([0.96] * 20)


def test_too_few_cycles_raises() -> None:
    with pytest.raises(StatisticalUncertaintyError, match="too few"):
        statistical_uncertainty_from_samples([1.0, 2.0, 3.0, 4.0, 5.0])


def test_unconverged_raises() -> None:
    with pytest.raises(StatisticalUncertaintyError, match="not converged"):
        statistical_uncertainty_from_samples(list(range(20)), converged=False)


def test_strong_autocorrelation_is_unreliable_not_fatal() -> None:
    """A heavily autocorrelated (near-monotone) tail: N_eff too small -> reliable False, still a value.

    'N_eff too small' is a soft flag, not a hard raise — the estimator returns an honest (wide)
    interval and the composer refuses it a thesis-grade tag.
    """
    x = np.cos(np.linspace(0.0, np.pi, 60))  # smooth monotone -> tiny N_eff (~5, below the floor)
    su = statistical_uncertainty_from_samples(x)
    assert su.n_eff < N_EFF_RELIABLE_MIN
    assert not su.reliable
    assert su.u95_statistical > 0.0


def test_student_t_table_and_conservative_rounding() -> None:
    assert _student_t_975(3) == 3.182
    assert _student_t_975(7) == 2.365
    # Between tabulated rows, round DOWN to the nearest df (larger t -> wider -> conservative).
    assert _student_t_975(35) == _student_t_975(30)
    with pytest.raises(StatisticalUncertaintyError):
        _student_t_975(0)


def test_integrated_autocorr_iid_near_half() -> None:
    rng = np.random.default_rng(7)
    tau = integrated_autocorr_time(rng.normal(0.0, 1.0, 500))
    assert 0.5 <= tau < 1.5  # IID limit is tau_int = 0.5


def test_wrapper_over_converged_cyclesamples() -> None:
    """The CycleSamples/report wrapper slices the converged tail and yields a positive u95."""
    rng = np.random.default_rng(11)
    n = 35
    # A converged limit cycle: small cycle-to-cycle mean scatter about 0.96, stable amplitude.
    means = 0.96 + rng.normal(0.0, 0.002, n)
    amps = np.full(n, 0.05)
    samples = CycleSamples(
        period=1.0,
        n_cycles=n,
        per_cycle_mean=tuple(float(v) for v in means),
        per_cycle_amplitude=tuple(float(v) for v in amps),
        per_cycle_min=tuple(float(m - a) for m, a in zip(means, amps, strict=True)),
        per_cycle_max=tuple(float(m + a) for m, a in zip(means, amps, strict=True)),
    )
    report = detect_cycle_convergence(samples)
    assert report.converged
    su = statistical_uncertainty(samples, report)
    assert su.u95_statistical > 0.0
    assert su.n_samples == report.n_converged_cycles

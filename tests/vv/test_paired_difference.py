"""Paired-difference ``u95_delta`` estimator — review-F1 known-answer tests (ADR-023).

Pure-host, hermetic (synthetic signals + fixed seeds), in the style of
``test_statistical_uncertainty.py`` (factor-~2 bands honest at NOBM's small batch counts).
The three known answers the finding demands:

* independent series  -> the diff-series u95 recovers the RSS of the two absolutes;
* strongly-correlated -> the diff-series u95 falls WELL below the RSS (the cancellation,
  measured — this is Invariant 10's prose turned into an assertion);
* an AR(1) difference series -> the diff's N_eff drops per the analytic ESS.

Plus every fail-loud path, the window bookkeeping, and the composed-RSS schema. This suite
backs the required ``small-signal-gate`` CI job.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from aero.postprocess.cycle_detection import CycleConvergenceReport
from aero.postprocess.phase_averaging import CycleSamples
from aero.vv.paired_difference import (
    PairedDifferenceError,
    paired_delta_uncertainty,
    paired_delta_uncertainty_from_samples,
)
from aero.vv.reportable import ComposedDeltaU95


def _cycles(means: np.ndarray, *, period: float = 1.0, amp: float = 0.05) -> CycleSamples:
    n = int(means.size)
    amps = np.full(n, amp)
    return CycleSamples(
        period=period,
        n_cycles=n,
        per_cycle_mean=tuple(float(v) for v in means),
        per_cycle_amplitude=tuple(float(a) for a in amps),
        per_cycle_min=tuple(float(m - a) for m, a in zip(means, amps, strict=True)),
        per_cycle_max=tuple(float(m + a) for m, a in zip(means, amps, strict=True)),
    )


def _report(n: int, start: int, *, converged: bool = True) -> CycleConvergenceReport:
    return CycleConvergenceReport(
        converged=converged,
        n_cycles=n,
        n_converged_cycles=(n - start) if converged else 0,
        converged_from_cycle=start if converged else n,
        mean_drift=0.001,
        amplitude_drift=0.001,
        mean_drift_tol=0.01,
        amplitude_drift_tol=0.02,
    )


# --- known answers -----------------------------------------------------------


def test_independent_series_recover_rss_of_absolutes() -> None:
    """No shared component -> no cancellation: u95_delta_statistical ~ RSS(u95_b, u95_c)."""
    rng = np.random.default_rng(0)
    n = 200
    b = 5.0 + rng.normal(0.0, 0.05, n)
    c = 5.2 + rng.normal(0.0, 0.05, n)
    p = paired_delta_uncertainty_from_samples(b, c, period=1.0)
    assert abs(p.correlation) < 0.3
    # variance_reduction = u95_diff / rss_independent -> ~1 for independence (factor-2 band).
    assert 0.5 <= p.variance_reduction <= 2.0


def test_strong_correlation_measures_the_cancellation() -> None:
    """A dominant shared component cancels in the difference: u95_delta WELL below the RSS.

    This is CONSTITUTION Invariant 10's 'correlated errors cancel... below the RSS of the two
    absolutes' turned from prose into a measured assertion (review F1).
    """
    rng = np.random.default_rng(3)
    n, sigma_ind = 200, 0.005
    shared = rng.normal(0.0, 0.10, n)
    b = 5.0 + shared + rng.normal(0.0, sigma_ind, n)
    c = 5.2 + shared + rng.normal(0.0, sigma_ind, n)
    p = paired_delta_uncertainty_from_samples(b, c, period=1.0)
    assert p.correlation > 0.95
    assert p.variance_reduction < 0.25
    assert p.cancellation_effective
    # The diff is IID noise of std sqrt(2)*sigma_ind: factor-2 band around the analytic width.
    analytic = 1.96 * math.sqrt(2.0) * sigma_ind / math.sqrt(n)
    assert 0.5 * analytic <= p.u95_delta_statistical <= 2.0 * analytic
    assert p.mean_delta == pytest.approx(0.2, abs=0.005)


def test_ar1_difference_series_reduces_n_eff() -> None:
    """An AR(1) DIFFERENCE series must drop the diff's N_eff (same band as the single-series suite)."""
    rng = np.random.default_rng(1)
    phi, n = 0.6, 400
    e = rng.normal(0.0, 1.0, n)
    d = np.zeros(n)
    for i in range(1, n):
        d[i] = phi * d[i - 1] + e[i]
    b = 5.0 + rng.normal(0.0, 1.0, n)
    c = b + 0.5 + d  # diff = 0.5 + AR(1): analytic ESS = N(1-phi)/(1+phi) = N/4
    p = paired_delta_uncertainty_from_samples(b, c, period=1.0, amp_scale=1.0)
    assert p.diff_stat.n_eff < 0.7 * n
    assert p.u95_delta_statistical > 0.0


def test_anticorrelation_surfaces_never_hides() -> None:
    """Failed cancellation (r < 0) is recorded and widens u95 — it must not raise or hide."""
    rng = np.random.default_rng(5)
    n = 200
    shared = rng.normal(0.0, 0.05, n)
    b = 5.0 + shared + rng.normal(0.0, 0.005, n)
    c = 5.2 - shared + rng.normal(0.0, 0.005, n)
    p = paired_delta_uncertainty_from_samples(b, c, period=1.0)
    assert p.correlation < 0.0
    assert p.variance_reduction > 1.0
    assert not p.cancellation_effective
    assert p.u95_delta_statistical > p.rss_independent  # honest and WIDE


# --- fail-loud paths ---------------------------------------------------------


def test_identical_tails_raise_self_comparison() -> None:
    x = np.linspace(1.0, 2.0, 20) + np.sin(np.arange(20))
    with pytest.raises(PairedDifferenceError, match="self-comparison"):
        paired_delta_uncertainty_from_samples(x, x.copy(), period=1.0)


def test_unequal_length_tails_raise() -> None:
    rng = np.random.default_rng(2)
    with pytest.raises(PairedDifferenceError, match="equal length"):
        paired_delta_uncertainty_from_samples(
            rng.normal(0.0, 1.0, 20), rng.normal(0.0, 1.0, 19), period=1.0
        )


def test_too_few_pairs_raises() -> None:
    rng = np.random.default_rng(2)
    with pytest.raises(PairedDifferenceError, match="too few"):
        paired_delta_uncertainty_from_samples(
            rng.normal(0.0, 1.0, 5), rng.normal(1.0, 1.0, 5), period=1.0
        )


def test_nan_in_tail_raises() -> None:
    rng = np.random.default_rng(2)
    b = rng.normal(0.0, 1.0, 20)
    c = rng.normal(1.0, 1.0, 20)
    c[7] = np.nan
    with pytest.raises(PairedDifferenceError, match="non-finite"):
        paired_delta_uncertainty_from_samples(b, c, period=1.0)


def test_alternating_tail_typed_error_not_zerodivision() -> None:
    """A period-locked alternating tail gives NOBM u95 == 0 (identical batch means): the
    degenerate per-side estimate must surface as a TYPED pairing error — never a bare
    mid-construction ValidationError, and never a ZeroDivisionError in variance_reduction."""
    rng = np.random.default_rng(4)
    b = np.tile([1.0, 2.0], 18)  # 36 cycles, batch means all exactly 1.5
    c = b + 0.5 + rng.normal(0.0, 0.01, 36)
    with pytest.raises(PairedDifferenceError, match="degenerate batch"):
        paired_delta_uncertainty_from_samples(b, c, period=1.0)


def test_dead_difference_raises_via_signal_scale() -> None:
    """Two runs differing only at float-noise level: the diff is dead AT SIGNAL SCALE."""
    rng = np.random.default_rng(6)
    b = 5.0 + rng.normal(0.0, 0.05, 40)
    c = b + 1.0e-15  # below float precision relative to the O(5) signal
    with pytest.raises(PairedDifferenceError, match="difference series"):
        paired_delta_uncertainty_from_samples(b, c, period=1.0, amp_scale=0.05)


# --- CycleSamples wrapper: alignment + window bookkeeping ---------------------


def _paired_wrapper_inputs(
    n_b: int = 40, n_c: int = 38, start_b: int = 3, start_c: int = 5
) -> tuple[CycleSamples, CycleConvergenceReport, CycleSamples, CycleConvergenceReport]:
    rng = np.random.default_rng(9)
    shared = rng.normal(0.0, 0.004, max(n_b, n_c))
    b = 0.96 + shared[:n_b] + rng.normal(0.0, 0.0015, n_b)
    c = 0.90 + shared[:n_c] + rng.normal(0.0, 0.0015, n_c)
    return _cycles(b), _report(n_b, start_b), _cycles(c), _report(n_c, start_c)


def test_wrapper_window_is_intersection_of_converged_tails() -> None:
    baseline, b_rep, candidate, c_rep = _paired_wrapper_inputs()
    p = paired_delta_uncertainty(baseline, b_rep, candidate, c_rep)
    assert p.pair_start == 5  # max(3, 5)
    assert p.n_pairs == 33  # min(40, 38) - 5
    assert p.baseline_stat.n_samples == p.n_pairs
    assert p.candidate_stat.n_samples == p.n_pairs
    assert p.diff_stat.n_samples == p.n_pairs
    assert p.period == 1.0


def test_wrapper_period_mismatch_raises() -> None:
    baseline, b_rep, candidate, c_rep = _paired_wrapper_inputs()
    candidate_off = candidate.model_copy(update={"period": 1.0001})
    with pytest.raises(PairedDifferenceError, match="period mismatch"):
        paired_delta_uncertainty(baseline, b_rep, candidate_off, c_rep)


def test_wrapper_unconverged_side_raises() -> None:
    baseline, b_rep, candidate, _ = _paired_wrapper_inputs()
    unconverged = _report(candidate.n_cycles, 0, converged=False)
    with pytest.raises(PairedDifferenceError, match="candidate run"):
        paired_delta_uncertainty(baseline, b_rep, candidate, unconverged)


def test_wrapper_window_too_small_raises() -> None:
    baseline, _, candidate, c_rep = _paired_wrapper_inputs()
    late = _report(baseline.n_cycles, 32)  # window = [32, 38) -> 6 pairs < 8
    with pytest.raises(PairedDifferenceError, match="common converged window"):
        paired_delta_uncertainty(baseline, late, candidate, c_rep)


def test_wrapper_report_samples_mismatch_raises() -> None:
    baseline, _b_rep, candidate, c_rep = _paired_wrapper_inputs()
    wrong = _report(baseline.n_cycles + 2, 3)
    with pytest.raises(PairedDifferenceError, match="mismatch"):
        paired_delta_uncertainty(baseline, wrong, candidate, c_rep)


# --- the composed RSS lives in the schema -------------------------------------


def test_composed_rss_delegates_to_paired_statistical_term() -> None:
    rng = np.random.default_rng(12)
    n = 100
    shared = rng.normal(0.0, 0.05, n)
    b = 5.0 + shared + rng.normal(0.0, 0.01, n)
    c = 5.3 + shared + rng.normal(0.0, 0.01, n)
    p = paired_delta_uncertainty_from_samples(b, c, period=1.0)
    stat = p.u95_delta_statistical
    only_stat = ComposedDeltaU95(u95_numerical=0.0, paired=p, u95_input=0.0)
    assert only_stat.u95_delta == pytest.approx(stat, rel=1.0e-15)
    full = ComposedDeltaU95(u95_numerical=0.003, paired=p, u95_input=0.004)
    assert full.u95_delta == pytest.approx(math.sqrt(0.003**2 + stat**2 + 0.004**2))


def test_composed_all_zero_contributions_rejected() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="positive contribution"):
        ComposedDeltaU95(u95_numerical=0.0, paired=None, u95_input=0.0)

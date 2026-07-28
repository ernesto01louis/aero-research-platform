"""The cumulative (linear-trend) drift bound in the shared PSS primitive.

This is the fix for the periodic-steady-state hole an adversarial review found in the
Stage-19 gate -- and, because `detect_cycle_convergence` also backs the Stage-11
moving-mesh gates, the bound lives in the shared primitive so the two cannot diverge.
The metric is a least-squares linear trend, not a first-to-last or block-means
difference, because a real limit cycle *beats* and any endpoint measure reads the beat's
phase rather than a trend. See the docstrings in `aero/postprocess/cycle_detection.py`.
"""

from __future__ import annotations

import numpy as np
import pytest
from aero.postprocess import detect_cycle_convergence
from aero.postprocess.cycle_detection import cumulative_drift
from aero.postprocess.phase_averaging import CycleSamples

pytestmark = pytest.mark.stage_19


def _samples(mean: tuple[float, ...], amp: tuple[float, ...]) -> CycleSamples:
    n = len(mean)
    return CycleSamples(
        period=1.0,
        n_cycles=n,
        per_cycle_mean=mean,
        per_cycle_amplitude=amp,
        per_cycle_min=tuple(m - a for m, a in zip(mean, amp, strict=True)),
        per_cycle_max=tuple(m + a for m, a in zip(mean, amp, strict=True)),
    )


def test_stationary_beating_is_not_drift() -> None:
    """A limit cycle whose amplitude wobbles around a fixed level has zero trend.

    This is the case the first-to-last and block-means metrics got wrong: their value
    depends on where the beat's endpoints fall, so a genuine converged cycle flips to
    "drifting". Amplitudes here oscillate 16-18 around 17 with no trend -- measured on a
    real historical plunging-airfoil run.
    """
    amp = (17.08, 16.25, 18.28, 17.02, 16.80, 16.47, 17.16, 16.27, 16.54, 16.41, 17.58, 16.70)
    _, amp_drift = cumulative_drift(np.zeros(len(amp)), np.array(amp))
    assert amp_drift < 0.02


def test_monotone_growth_is_drift() -> None:
    """A steady 1.2 %/cycle rise reads well above the bound even though every
    adjacent step is inside a 2 % tolerance."""
    amp = tuple(1.0 * 1.012**i for i in range(22))
    _, amp_drift = cumulative_drift(np.ones(len(amp)), np.array(amp))
    assert amp_drift > 0.02


def test_default_gate_is_off_and_byte_identical() -> None:
    """Passing no cumulative tolerance must not change `converged` -- the historical
    Stage-11 behaviour is preserved unless a caller opts in."""
    amp = tuple(1.0 * 1.012**i for i in range(22))
    samples = _samples(tuple(0.0 for _ in amp), amp)
    assert detect_cycle_convergence(samples).converged
    # The cumulative drift is REPORTED even when not gated on.
    assert detect_cycle_convergence(samples).cumulative_amplitude_drift > 0.02


def test_opt_in_gate_refuses_growth() -> None:
    amp = tuple(1.0 * 1.012**i for i in range(22))
    samples = _samples(tuple(0.0 for _ in amp), amp)
    gated = detect_cycle_convergence(samples, cumulative_amplitude_drift_tol=0.02)
    assert not gated.converged
    assert gated.cumulative_amplitude_drift_tol == 0.02


def test_opt_in_gate_accepts_a_stationary_cycle() -> None:
    """A bound that refused real data would be worse than no bound."""
    amp = (1.00, 0.99, 1.01, 1.00, 0.99, 1.01, 1.00, 1.00, 0.99, 1.01, 1.00, 1.00)
    samples = _samples(tuple(0.0 for _ in amp), amp)
    gated = detect_cycle_convergence(
        samples, cumulative_mean_drift_tol=0.02, cumulative_amplitude_drift_tol=0.02
    )
    assert gated.converged

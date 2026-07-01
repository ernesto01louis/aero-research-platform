"""Stage 11 — aero.postprocess.cycle_detection (periodic-steady-state)."""

from __future__ import annotations

import pytest
from aero.postprocess import detect_cycle_convergence
from aero.postprocess.phase_averaging import CycleSamples

pytestmark = pytest.mark.stage_11


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


def test_steady_sequence_converges_from_first_cycle() -> None:
    rep = detect_cycle_convergence(_samples((1.0,) * 8, (0.5,) * 8))
    assert rep.converged
    assert rep.converged_from_cycle == 0
    assert rep.n_converged_cycles == 8


def test_growing_then_flat_amplitude_converges_partway() -> None:
    # Zero-mean oscillation (cylinder lift): amplitude grows then saturates.
    amp = (0.1, 0.3, 0.6, 0.9, 1.0, 1.0, 1.0, 1.0)
    rep = detect_cycle_convergence(_samples((0.0,) * 8, amp))
    assert rep.converged
    assert rep.converged_from_cycle == 4
    assert rep.n_converged_cycles == 4


def test_monotone_drift_never_converges() -> None:
    rep = detect_cycle_convergence(_samples(tuple(float(i) for i in range(1, 9)), (0.5,) * 8))
    assert not rep.converged
    assert rep.n_converged_cycles == 0
    assert rep.mean_drift > rep.mean_drift_tol


def test_short_settled_tail_is_not_enough() -> None:
    # Only the last 2 cycles settle; window+1 = 4 required -> not converged.
    amp = (0.1, 0.3, 0.6, 0.9, 1.0, 1.0)
    rep = detect_cycle_convergence(_samples((0.0,) * 6, amp))
    assert not rep.converged


def test_single_cycle_cannot_converge() -> None:
    rep = detect_cycle_convergence(_samples((1.0,), (0.5,)))
    assert not rep.converged
    assert rep.n_cycles == 1

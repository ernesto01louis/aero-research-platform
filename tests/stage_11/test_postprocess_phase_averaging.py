"""Stage 11 — aero.postprocess.phase_averaging (cycle segmentation + phase-average)."""

from __future__ import annotations

import numpy as np
import pytest
from aero.postprocess import Signal, phase_average, segment_cycles
from aero.postprocess.phase_averaging import CycleSamples

pytestmark = pytest.mark.stage_11


def _heave_signal(*, periods: int = 6, amp: float = 0.4, mean: float = 0.2) -> Signal:
    # period = 1.0; 200 samples per period.
    t = np.linspace(0.0, float(periods), periods * 200 + 1)
    y = mean + amp * np.sin(2 * np.pi * t)
    return Signal.from_arrays(t, y, name="cl")


def test_segment_cycles_counts_and_stats() -> None:
    samples = segment_cycles(_heave_signal(periods=6), period=1.0)
    assert isinstance(samples, CycleSamples)
    assert samples.n_cycles == 6
    assert all(m == pytest.approx(0.2, abs=1e-3) for m in samples.per_cycle_mean)
    assert all(a == pytest.approx(0.4, abs=2e-3) for a in samples.per_cycle_amplitude)


def test_segment_cycles_drop_initial() -> None:
    samples = segment_cycles(_heave_signal(periods=6), period=1.0, drop_initial_cycles=2)
    assert samples.n_cycles == 4  # 6 - 2 dropped


def test_segment_cycles_underresolved_fails_loud() -> None:
    t = np.linspace(0.0, 3.0, 12)  # 4 samples/period
    y = np.sin(2 * np.pi * t)
    with pytest.raises(ValueError, match="samples"):
        segment_cycles(Signal.from_arrays(t, y, name="cl"), period=1.0, min_samples_per_cycle=8)


def test_segment_cycles_needs_a_full_cycle() -> None:
    t = np.linspace(0.0, 0.5, 20)
    y = np.sin(2 * np.pi * t)
    with pytest.raises(ValueError, match="< 1 cycle"):
        segment_cycles(Signal.from_arrays(t, y, name="cl"), period=1.0)


def test_phase_average_recovers_waveform() -> None:
    pa = phase_average(_heave_signal(periods=6, amp=0.4, mean=0.2), period=1.0, n_bins=16)
    assert pa.n_cycles == 6
    assert max(pa.mean) == pytest.approx(0.6, abs=0.02)  # mean + amp
    assert min(pa.mean) == pytest.approx(-0.2, abs=0.02)  # mean - amp
    # Identical cycles -> near-zero cycle-to-cycle scatter.
    assert max(pa.std) < 0.02

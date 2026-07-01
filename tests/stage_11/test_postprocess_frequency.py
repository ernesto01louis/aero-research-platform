"""Stage 11 — aero.postprocess.frequency (FFT + parabolic peak interpolation).

Pins that the promoted Strouhal helper recovers a known frequency to sub-bin accuracy
(the Stage-10 behaviour, now solver-agnostic) and that the Strouhal wrapper composes
f * length / velocity correctly.
"""

from __future__ import annotations

import numpy as np
import pytest
from aero.postprocess import Signal, dominant_frequency, strouhal
from aero.postprocess.frequency import FrequencyEstimate

pytestmark = pytest.mark.stage_11


def _sine(freq: float, *, n: int = 600, tmax: float = 120.0, mean: float = 0.0) -> Signal:
    t = np.linspace(0.0, tmax, n)
    y = 0.3 * np.sin(2 * np.pi * freq * t) + mean + 0.02 * np.cos(2 * np.pi * 2 * freq * t)
    return Signal.from_arrays(t, y, name="lift_coefficient")


def test_dominant_frequency_subbin_accuracy() -> None:
    est = dominant_frequency(_sine(0.165, mean=0.12))
    assert isinstance(est, FrequencyEstimate)
    assert est.frequency == pytest.approx(0.165, abs=0.002)
    assert est.peak_amplitude > 0.0
    assert est.n_samples == 600


def test_strouhal_composes_length_over_velocity() -> None:
    est = strouhal(_sine(0.33), length=2.0, velocity=4.0)
    # St = f * L / U = 0.33 * 2 / 4 = 0.165
    assert est.strouhal == pytest.approx(0.165, abs=0.003)
    assert est.frequency == pytest.approx(0.33, abs=0.004)


def test_strouhal_rejects_nonpositive_scales() -> None:
    with pytest.raises(ValueError, match="positive length"):
        strouhal(_sine(0.2), length=0.0, velocity=1.0)


def test_dominant_frequency_matches_legacy_helper() -> None:
    # Same math as the Stage-10 _strouhal_from_signal (regression against the adapter).
    from aero.adapters.openfoam.solver import _strouhal_from_signal

    t = np.linspace(0.0, 120.0, 600)
    cl = 0.3 * np.sin(2 * np.pi * 0.165 * t) + 0.12
    legacy = _strouhal_from_signal(t, cl, diameter=1.0, u_inf=1.0)
    new = strouhal(Signal.from_arrays(t, cl, name="cl"), length=1.0, velocity=1.0).strouhal
    assert new == pytest.approx(legacy, rel=1e-9)

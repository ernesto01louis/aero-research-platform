"""Frequency / Strouhal extraction from a scalar time series.

Promotes the Stage-10 ``aero.adapters.openfoam.solver._strouhal_from_signal`` FFT
helper (with its parabolic peak interpolation for sub-bin accuracy) into a
solver-agnostic, typed toolkit function. The math is identical, so the Stage-10
cylinder Strouhal result is preserved bit-for-bit; the difference is that this
version works on any :class:`~aero.postprocess._base.Signal` (a plunging foil's
forcing frequency, a shedding cylinder, ...), not only the cylinder.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, Field

from aero.postprocess._base import _STRICT, Signal


class FrequencyEstimate(BaseModel):
    """The dominant non-DC frequency of a signal, with its Strouhal number."""

    model_config = _STRICT

    frequency: float = Field(..., ge=0.0, description="Dominant non-DC frequency [1/time].")
    strouhal: float | None = Field(
        default=None, description="f * length / velocity, if a length/velocity was supplied."
    )
    peak_amplitude: float = Field(..., ge=0.0, description="FFT amplitude at the dominant bin.")
    n_samples: int = Field(..., ge=4, description="Number of time samples used.")


def dominant_frequency(sig: Signal, *, detrend: bool = True) -> FrequencyEstimate:
    """Dominant non-DC frequency of ``sig`` via a real FFT + parabolic peak interp.

    Detrends the signal (removes the mean so the DC bin does not dominate), takes the
    real FFT over the near-uniform samples, finds the largest non-DC bin, and refines
    the peak with parabolic interpolation around it — the FFT bin width ``1/T`` would
    otherwise cap frequency precision at a few percent. Raises if there are too few
    samples to resolve a peak.
    """
    t = sig.t_array
    y = sig.y_array
    n = len(t)
    if detrend:
        y = y - y.mean()
    dt = float((t[-1] - t[0]) / (n - 1))  # mean sample spacing
    freqs = np.fft.rfftfreq(n, d=dt)
    amp = np.abs(np.fft.rfft(y))
    if len(amp) < 4:
        raise ValueError(
            f"signal {sig.name!r} has too few samples ({n}) to resolve a dominant frequency via FFT"
        )
    peak = int(np.argmax(amp[1:])) + 1  # skip the DC bin
    df = float(freqs[1] - freqs[0])
    f_peak = float(freqs[peak])
    # Parabolic interpolation around the peak bin -> sub-bin frequency accuracy.
    if 0 < peak < len(amp) - 1:
        a0, a1, a2 = amp[peak - 1], amp[peak], amp[peak + 1]
        denom = a0 - 2.0 * a1 + a2
        if denom != 0.0:
            f_peak += df * 0.5 * float((a0 - a2) / denom)
    return FrequencyEstimate(
        frequency=max(f_peak, 0.0),
        peak_amplitude=float(amp[peak]),
        n_samples=n,
    )


def strouhal(sig: Signal, *, length: float, velocity: float) -> FrequencyEstimate:
    """Strouhal number ``St = f * length / velocity`` from the dominant frequency.

    For a shedding cylinder ``length`` is the diameter; for a bluff body it is the
    projected height. ``velocity`` is the freestream speed. Returns the full
    :class:`FrequencyEstimate` with ``strouhal`` populated.
    """
    if length <= 0.0 or velocity <= 0.0:
        raise ValueError(f"strouhal needs positive length ({length}) and velocity ({velocity})")
    est = dominant_frequency(sig)
    return est.model_copy(update={"strouhal": est.frequency * length / velocity})

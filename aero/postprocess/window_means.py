"""Time-weighted window means of an irregularly-sampled scalar signal (Stage 16).

The URANS certification path time-averages force coefficients written every (adaptive)
timestep. With ``adjustTimeStep`` the samples are NOT equally spaced, so a plain sample mean
is biased toward small-timestep intervals; the honest window mean is the time integral over
the window divided by its duration (trapezoid). The per-window means feed the NOBM sampling
estimator (`statistical_uncertainty_from_samples`) — windows play the role cycles play in the
flapping path (there is no imposed period for a statically loaded airfoil).
"""

from __future__ import annotations

import itertools

import numpy as np

__all__ = ["time_weighted_window_means"]


def time_weighted_window_means(
    t: tuple[float, ...] | list[float],
    x: tuple[float, ...] | list[float],
    *,
    start_time: float,
    n_windows: int,
) -> tuple[float, ...]:
    """Means of ``x`` over ``n_windows`` equal-duration windows spanning ``[start_time, t[-1]]``.

    Each mean is the trapezoid time-integral over the window divided by the window duration
    (interpolating ``x`` onto the window edges so windows tile exactly). FAIL-LOUD on a
    non-increasing time axis, a start time outside the series, or windows too short to
    contain at least two samples.
    """
    if n_windows < 2:
        raise ValueError(f"time_weighted_window_means: need >= 2 windows, got {n_windows}")
    ta = np.asarray(t, dtype=np.float64)
    xa = np.asarray(x, dtype=np.float64)
    if ta.ndim != 1 or ta.shape != xa.shape:
        raise ValueError("time_weighted_window_means: t and x must be equal-length 1-D series")
    if np.any(np.diff(ta) <= 0.0):
        raise ValueError("time_weighted_window_means: time axis must be strictly increasing")
    if not (ta[0] <= start_time < ta[-1]):
        raise ValueError(
            f"time_weighted_window_means: start_time {start_time} outside series "
            f"[{ta[0]}, {ta[-1]})"
        )
    edges = np.linspace(start_time, float(ta[-1]), n_windows + 1)
    means: list[float] = []
    for lo, hi in itertools.pairwise(edges):
        inside = (ta > lo) & (ta < hi)
        if int(inside.sum()) < 2:
            raise ValueError(
                f"time_weighted_window_means: window [{lo:.6g}, {hi:.6g}] contains "
                f"{int(inside.sum())} samples (< 2) — too few windows or too short a tail."
            )
        # Tile exactly: interpolate onto the window edges, integrate inside.
        tw = np.concatenate(([lo], ta[inside], [hi]))
        xw = np.concatenate(([np.interp(lo, ta, xa)], xa[inside], [np.interp(hi, ta, xa)]))
        means.append(float(np.trapezoid(xw, tw) / (hi - lo)))
    return tuple(means)

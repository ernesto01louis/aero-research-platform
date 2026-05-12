"""NACA 4-digit airfoil generator (NASA TMR sharp-trailing-edge variant).

Reference: https://turbmodels.larc.nasa.gov/naca0012_val.html

The standard NACA 4-digit thickness polynomial is

    y/c = 5 t [a0 sqrt(x/c) + a1 (x/c) + a2 (x/c)^2 + a3 (x/c)^3 + a4 (x/c)^4]

with the canonical coefficients (a0..a4) = (0.2969, -0.1260, -0.3516, 0.2843,
-0.1015). At x/c = 1 the polynomial evaluates to y/c ~ 1.26e-3, i.e. a small
but non-zero blunt trailing edge. The NASA TMR validation cases redefine the
trailing edge by extending the chord to x = 1.008930411365 c, at which point
the standard polynomial closes to y = 0 within rounding noise. Every NASA TMR
NACA-0012 grid family (Family I, II, III) uses this sharp-TE definition.
"""

from __future__ import annotations

from typing import Final

import numpy as np

# Standard NACA 4-digit thickness polynomial coefficients.
_A: Final[tuple[float, float, float, float, float]] = (
    0.2969,
    -0.1260,
    -0.3516,
    0.2843,
    -0.1015,
)

# x-coordinate (chord units) at which the standard NACA-4 polynomial closes
# to zero thickness. Sourced from NASA TMR's NACA-0012 sharp-TE redefinition.
NACA_SHARP_TE_X: Final[float] = 1.008930411365


def thickness(x: np.ndarray, t: float) -> np.ndarray:
    """Half-thickness y(x) of a NACA 4-digit airfoil with chord = 1.

    Args:
        x: chordwise coordinates, any non-negative values.
        t: max thickness as a fraction of chord (e.g. 0.12 for NACA 0012).

    Returns:
        y values matching the shape of ``x``.
    """
    xa = np.asarray(x, dtype=np.float64)
    a0, a1, a2, a3, a4 = _A
    sqrt_x = np.sqrt(np.maximum(xa, 0.0))
    return 5.0 * t * (a0 * sqrt_x + a1 * xa + a2 * xa**2 + a3 * xa**3 + a4 * xa**4)


def naca_half(
    t: float = 0.12,
    n_points: int = 257,
    x_te: float = NACA_SHARP_TE_X,
) -> tuple[np.ndarray, np.ndarray]:
    """Symmetric NACA-4 half profile with cosine-clustered chordwise spacing.

    Cosine clustering packs points near the leading and trailing edges where
    curvature and pressure gradients are large; matches the NASA TMR Family-I
    grid's chordwise spacing pattern.
    """
    if n_points < 3:
        raise ValueError("n_points must be >= 3")
    if not 0.0 < t < 1.0:
        raise ValueError("t must lie in (0, 1)")
    if x_te <= 0.0:
        raise ValueError("x_te must be positive")
    theta = np.linspace(0.0, np.pi, n_points)
    x = 0.5 * x_te * (1.0 - np.cos(theta))
    y = thickness(x, t)
    # Snap LE and TE to exact zero to suppress rounding noise (~1e-18 / 1e-9).
    y[0] = 0.0
    y[-1] = 0.0
    return x, y


def naca_closed_loop(
    t: float = 0.12,
    n_per_side: int = 257,
    x_te: float = NACA_SHARP_TE_X,
) -> tuple[np.ndarray, np.ndarray]:
    """Closed clockwise NACA-4 loop: upper TE→LE, then lower LE→TE.

    The leading-edge point is shared between the two halves; total point
    count is ``2*n_per_side - 1``.
    """
    x, yhalf = naca_half(t=t, n_points=n_per_side, x_te=x_te)
    x_upper = x[::-1]
    y_upper = yhalf[::-1]
    x_lower = x[1:]
    y_lower = -yhalf[1:]
    return np.concatenate([x_upper, x_lower]), np.concatenate([y_upper, y_lower])

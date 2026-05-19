"""Analytic geometry for the NASA TMR verification cases.

The turbulent flat plate needs no curve (a straight wall). The 2D
bump-in-channel has a smooth analytic bump on the lower wall, defined here in
closed form so the surface is fully reproducible — no opaque mesh asset.

The bump follows the NASA TMR "2D Bump-in-channel" definition: a bump of
height `height` spanning `0 <= x <= bump_length`, tangent to the flat wall at
both ends,

    y_wall(x) = height * sin^4( pi * x / bump_length )      0 <= x <= bump_length
    y_wall(x) = 0                                           otherwise

The default `height = 0.05`, `bump_length = 1.5` are the TMR values.
Reference: https://turbmodels.larc.nasa.gov/bump.html
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

BUMP_HEIGHT = 0.05
BUMP_LENGTH = 1.5


def bump_height_at(
    x: NDArray[np.float64],
    *,
    height: float = BUMP_HEIGHT,
    bump_length: float = BUMP_LENGTH,
) -> NDArray[np.float64]:
    """Lower-wall height of the TMR 2D bump at chordwise stations `x`."""
    xa = np.asarray(x, dtype=np.float64)
    on_bump = (xa >= 0.0) & (xa <= bump_length)
    y = np.zeros_like(xa)
    y[on_bump] = height * np.sin(np.pi * xa[on_bump] / bump_length) ** 4
    return np.asarray(y, dtype=np.float64)


def bump_lower_wall(
    n_points: int,
    *,
    x_start: float,
    x_end: float,
    height: float = BUMP_HEIGHT,
    bump_length: float = BUMP_LENGTH,
) -> NDArray[np.float64]:
    """(x, y) points along the bump lower wall, inlet to outlet.

    Points are uniformly spaced in `x` from `x_start` to `x_end`; the wall is
    flat outside `[0, bump_length]` and follows the analytic bump within it.
    """
    if n_points < 2:
        raise ValueError(f"n_points must be >= 2, got {n_points}")
    x = np.linspace(x_start, x_end, n_points)
    y = bump_height_at(x, height=height, bump_length=bump_length)
    return np.asarray(np.column_stack([x, y]), dtype=np.float64)

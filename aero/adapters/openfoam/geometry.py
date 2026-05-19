"""Analytic NACA 0012 geometry.

The Stage 03 reference case uses a 2D `blockMesh` C-grid, which needs the
airfoil surface as a curve — no STL is involved (STL is a `snappyHexMesh`
concern, Stage 06+). Generating the profile from the closed-form NACA
4-digit equation keeps the geometry fully reproducible: there is no opaque
binary asset, and the surface is recomputable from `n_points` alone.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

# NACA 0012: maximum thickness 12% of chord.
_THICKNESS = 0.12
# Closed-trailing-edge quartic coefficient. The open-TE value is 0.1015;
# 0.1036 closes the trailing edge to a point, which a hand-built C-grid
# needs (a blunt finite-thickness TE has no single TE vertex).
_A4_CLOSED_TE = 0.1036


def naca0012_half_thickness(x: NDArray[np.float64], *, chord: float = 1.0) -> NDArray[np.float64]:
    """Half-thickness of a closed-TE NACA 0012 at chordwise stations `x`."""
    xc = np.asarray(x, dtype=np.float64) / chord
    yt = (
        5.0
        * _THICKNESS
        * (
            0.2969 * np.sqrt(xc)
            - 0.1260 * xc
            - 0.3516 * xc**2
            + 0.2843 * xc**3
            - _A4_CLOSED_TE * xc**4
        )
    )
    return np.asarray(yt * chord, dtype=np.float64)


def naca0012_coordinates(n_points: int = 120, *, chord: float = 1.0) -> NDArray[np.float64]:
    """Upper-surface (x, y) coordinates of a NACA 0012, leading edge to trailing edge.

    Stations are cosine-spaced, clustering points at the leading and trailing
    edges where curvature is highest. The lower surface is the mirror image
    (y -> -y); the symmetric section makes that exact.
    """
    if n_points < 2:
        raise ValueError(f"n_points must be >= 2, got {n_points}")
    beta = np.linspace(0.0, np.pi, n_points)
    x = 0.5 * (1.0 - np.cos(beta)) * chord
    y = naca0012_half_thickness(x, chord=chord)
    # Snap the leading and trailing edges exactly onto the chord line.
    y[0] = 0.0
    y[-1] = 0.0
    return np.asarray(np.column_stack([x, y]), dtype=np.float64)


def write_coordinates_csv(path: str, coords: NDArray[np.float64]) -> None:
    """Write (x, y) surface coordinates to a CSV with an `x,y` header."""
    np.savetxt(path, coords, delimiter=",", header="x,y", comments="", fmt="%.10f")

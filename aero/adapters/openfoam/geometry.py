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
# Trailing-edge quartic coefficients. 0.1036 closes the TE to a point (the
# Stage-05 sharp-TE C-grid default); 0.1015 is the standard NACA 0012 open
# (blunt) TE, leaving ~0.00252c finite thickness. Stage 09's blunt-TE pass
# splits the singular TE vertex to kill the +21% pressure-drag error (ADR-012;
# the resolution-milestone for tests/vv/test_tmr_naca0012.py).
_A4_CLOSED_TE = 0.1036
_A4_OPEN_TE = 0.1015


def naca0012_half_thickness(
    x: NDArray[np.float64], *, chord: float = 1.0, a4: float = _A4_CLOSED_TE
) -> NDArray[np.float64]:
    """Half-thickness of a NACA 0012 at chordwise stations `x`.

    ``a4`` selects the trailing-edge closure: ``_A4_CLOSED_TE`` (default) closes
    to a point; ``_A4_OPEN_TE`` leaves the standard finite-thickness blunt TE.
    """
    xc = np.asarray(x, dtype=np.float64) / chord
    yt = (
        5.0
        * _THICKNESS
        * (0.2969 * np.sqrt(xc) - 0.1260 * xc - 0.3516 * xc**2 + 0.2843 * xc**3 - a4 * xc**4)
    )
    return np.asarray(yt * chord, dtype=np.float64)


# The full base thickness (both TE corners) the standard open-TE geometry leaves
# at x=c, in chords (~0.00252c). The blunt-TE C-grid meshes exactly this fixed
# geometry; `CaseSpec.trailing_edge_thickness` records it and is validated
# against it (a value that does not match the geometry fails loud — the field is
# not a free knob, it documents the open-TE the mesh actually uses).
OPEN_TE_FULL_THICKNESS: float = float(
    2.0 * naca0012_half_thickness(np.asarray([1.0], dtype=np.float64), a4=_A4_OPEN_TE)[0]
)


def naca0012_coordinates(
    n_points: int = 120, *, chord: float = 1.0, blunt_te: bool = False
) -> NDArray[np.float64]:
    """Upper-surface (x, y) coordinates of a NACA 0012, leading edge to trailing edge.

    Stations are cosine-spaced, clustering points at the leading and trailing
    edges where curvature is highest. The lower surface is the mirror image
    (y -> -y); the symmetric section makes that exact.

    ``blunt_te=False`` (default) closes the TE to a point — the sharp-TE C-grid.
    ``blunt_te=True`` uses the standard open-TE coefficient and leaves the finite
    TE half-thickness at ``x=chord``; the upper/lower endpoints become the two TE
    corners the Stage-09 blunt-TE C-grid splits apart.
    """
    if n_points < 2:
        raise ValueError(f"n_points must be >= 2, got {n_points}")
    a4 = _A4_OPEN_TE if blunt_te else _A4_CLOSED_TE
    beta = np.linspace(0.0, np.pi, n_points)
    x = 0.5 * (1.0 - np.cos(beta)) * chord
    y = naca0012_half_thickness(x, chord=chord, a4=a4)
    # Snap the leading edge onto the chord line; snap the TE too unless it's blunt.
    y[0] = 0.0
    if not blunt_te:
        y[-1] = 0.0
    return np.asarray(np.column_stack([x, y]), dtype=np.float64)


# NACA-4 baseline: zero camber, 12% thickness. `naca4_coordinates(max_camber=0,
# max_thickness_frac=0.12)` is byte-identical to `naca0012_coordinates` — the shape-optimizer's
# baseline recovery, so a matched-condition delta against the NACA 0012 is exact (Stage 15).
_BASELINE_THICKNESS_FRAC = _THICKNESS


def naca4_coordinates(
    n_points: int = 120,
    *,
    chord: float = 1.0,
    max_camber: float = 0.0,
    camber_position: float = 0.4,
    max_thickness_frac: float = _BASELINE_THICKNESS_FRAC,
    blunt_te: bool = False,
    surface: str = "upper",
) -> NDArray[np.float64]:
    """NACA 4-digit (x, y) coordinates with camber + thickness as shape design variables.

    The shape-optimization generalisation of :func:`naca0012_coordinates`. Thickness is applied
    **normal to the chord line (y-only)** on the SAME cosine-spaced x-stations, so the mesh
    topology (block/cell counts, LE/mid/TE corner x-positions) is invariant under a shape change —
    exactly what a matched-condition optimization delta needs. Returns the ``"upper"`` or
    ``"lower"`` surface, leading edge to trailing edge.

    * ``max_camber`` (m) — max camber as a fraction of chord (0 = symmetric NACA-00xx).
    * ``camber_position`` (p) — chordwise position of max camber, fraction of chord.
    * ``max_thickness_frac`` (t) — max thickness / chord; 0.12 = NACA 0012.

    At ``max_camber=0, max_thickness_frac=0.12`` the ``"upper"`` surface is byte-identical to
    :func:`naca0012_coordinates` (and ``"lower"`` is its exact mirror). FAIL-LOUD if the camber
    parameters would collapse the section (non-positive thickness anywhere).
    """
    if n_points < 2:
        raise ValueError(f"n_points must be >= 2, got {n_points}")
    if surface not in ("upper", "lower"):
        raise ValueError(f"surface must be 'upper' or 'lower', got {surface!r}")
    if not 0.0 < camber_position < 1.0:
        raise ValueError(f"camber_position must be in (0,1), got {camber_position}")

    a4 = _A4_OPEN_TE if blunt_te else _A4_CLOSED_TE
    beta = np.linspace(0.0, np.pi, n_points)
    x = 0.5 * (1.0 - np.cos(beta)) * chord  # SAME stations as naca0012_coordinates
    # Half-thickness scaled from the 12% baseline quartic to the requested t/c.
    yt = naca0012_half_thickness(x, chord=chord, a4=a4) * (max_thickness_frac / _THICKNESS)

    xc = x / chord
    m, p = max_camber, camber_position
    if m == 0.0:
        yc = np.zeros_like(x)
    else:
        yc = (
            np.where(
                xc < p,
                (m / p**2) * (2.0 * p * xc - xc**2),
                (m / (1.0 - p) ** 2) * ((1.0 - 2.0 * p) + 2.0 * p * xc - xc**2),
            )
            * chord
        )

    y = yc + yt if surface == "upper" else yc - yt
    # Snap the LE onto the origin; snap the TE closed unless blunt (yc(0)=yc(1)=0, yt(1)=0 sharp).
    y[0] = 0.0
    if not blunt_te:
        y[-1] = 0.0
    # FAIL-LOUD: the section must keep positive half-thickness in the interior (0 only at LE/TE;
    # a tiny negative float at the TE is numerically zero, hence the -1e-9 tolerance).
    if float(np.min(yt)) < -1.0e-9:
        raise ValueError(f"non-positive thickness (max_thickness_frac={max_thickness_frac})")
    return np.asarray(np.column_stack([x, y]), dtype=np.float64)


def write_coordinates_csv(path: str, coords: NDArray[np.float64]) -> None:
    """Write (x, y) surface coordinates to a CSV with an `x,y` header."""
    np.savetxt(path, coords, delimiter=",", header="x,y", comments="", fmt="%.10f")

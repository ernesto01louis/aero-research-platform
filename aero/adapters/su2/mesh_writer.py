"""Native `.su2` mesh generation for the SU2 adapter.

SU2 reads a native ASCII `.su2` mesh; OpenFOAM reads a `polyMesh` directory.
Each adapter handles its own mesh format internally (the platform `CaseSpec`
is mesh-format-agnostic above the adapter). This module builds structured
quad meshes for the geometries the platform defines analytically and emits
them as `.su2`:

* `airfoil_ogrid` — an O-grid around the analytic NACA 0012 profile (the TMR
  NACA 0012 and the transonic NACA 0012 cases);
* `flat_plate_grid` — the TMR turbulent flat plate;
* `bump_grid` — the TMR 2D bump-in-channel.

Wall-normal spacing is geometric, sized to a requested first-cell height so
the boundary layer is wall-resolved (y+ ~ 1), mirroring the OpenFOAM C-grid.
A pre-supplied `.su2` asset (the 3D ONERA M6 wing) bypasses this module — see
`SU2Solver._write_case`.

`.su2` element type codes are VTK-based: 9 = quadrilateral, 3 = line.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from aero.adapters.openfoam.geometry import naca0012_coordinates
from aero.adapters.openfoam.tmr_geometry import bump_height_at

_QUAD = 9  # .su2 / VTK element code for a quadrilateral
_LINE = 3  # .su2 / VTK element code for a line (boundary) element

# A marker is a named list of boundary line elements (pairs of point indices).
Marker = tuple[str, list[tuple[int, int]]]


def geometric_spacing(n_cells: int, first: float, total: float) -> NDArray[np.float64]:
    """Cumulative node positions 0..`total` with `n_cells` geometrically-grown cells.

    The first cell has height `first`; the growth ratio is solved so the cells
    sum exactly to `total`. Returns `n_cells + 1` ascending positions. This is
    what makes the SU2 mesh wall-resolved at a requested y+.
    """
    if n_cells < 1:
        raise ValueError(f"n_cells must be >= 1, got {n_cells}")
    if not 0 < first < total:
        raise ValueError(f"need 0 < first ({first}) < total ({total})")
    if n_cells * first >= total:
        # Uniform spacing already overshoots — fall back to uniform.
        return np.linspace(0.0, total, n_cells + 1)

    def _summed(r: float) -> float:
        return first * n_cells if abs(r - 1.0) < 1e-12 else first * (r**n_cells - 1.0) / (r - 1.0)

    lo, hi = 1.0, 2.0
    while _summed(hi) < total:
        hi *= 1.5
    for _ in range(200):  # bisection on the growth ratio
        mid = 0.5 * (lo + hi)
        if _summed(mid) < total:
            lo = mid
        else:
            hi = mid
    r = 0.5 * (lo + hi)
    heights = first * r ** np.arange(n_cells)
    pos = np.concatenate([[0.0], np.cumsum(heights)])
    pos *= total / pos[-1]  # snap the last node exactly onto `total`
    return np.asarray(pos, dtype=np.float64)


def _signed_area(loop: NDArray[np.float64]) -> float:
    """Shoelace signed area of a closed polygon given as ordered (x, y) points."""
    x, y = loop[:, 0], loop[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _write_su2(
    path: Path,
    *,
    points: NDArray[np.float64],
    quads: list[tuple[int, int, int, int]],
    markers: list[Marker],
) -> None:
    """Emit a 2D structured quad mesh as a native `.su2` ASCII file."""
    lines: list[str] = ["NDIME= 2", f"NELEM= {len(quads)}"]
    lines += [f"{_QUAD} {a} {b} {c} {d}" for a, b, c, d in quads]
    lines.append(f"NPOIN= {len(points)}")
    lines += [f"{x:.10f} {y:.10f}" for x, y in points]
    lines.append(f"NMARK= {len(markers)}")
    for name, elems in markers:
        lines.append(f"MARKER_TAG= {name}")
        lines.append(f"MARKER_ELEMS= {len(elems)}")
        lines += [f"{_LINE} {a} {b}" for a, b in elems]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _structured_quads(ni: int, nj: int, *, periodic_i: bool) -> list[tuple[int, int, int, int]]:
    """Quad connectivity for an `ni`x`nj` structured grid (node index `i*nj + j`).

    Quads are wound counter-clockwise. `periodic_i` wraps the last i-column
    onto the first (an O-grid); otherwise the i-direction is open.
    """

    def idx(i: int, j: int) -> int:
        return i * nj + j

    quads: list[tuple[int, int, int, int]] = []
    i_max = ni if periodic_i else ni - 1
    for i in range(i_max):
        ip = (i + 1) % ni
        for j in range(nj - 1):
            quads.append((idx(i, j), idx(ip, j), idx(ip, j + 1), idx(i, j + 1)))
    return quads


def _edge_line(
    ni: int, nj: int, *, i: int | None = None, j: int | None = None
) -> list[tuple[int, int]]:
    """Boundary line elements along the grid edge at fixed `i` or fixed `j`."""

    def idx(ii: int, jj: int) -> int:
        return ii * nj + jj

    if j is not None:
        return [(idx(i_, j), idx(i_ + 1, j)) for i_ in range(ni - 1)]
    assert i is not None
    return [(idx(i, j_), idx(i, j_ + 1)) for j_ in range(nj - 1)]


# --- airfoil O-grid -----------------------------------------------------------
def _closed_airfoil_loop(n_surface: int, chord: float) -> NDArray[np.float64]:
    """A closed NACA 0012 loop of `n_surface` points, trailing edge first.

    Ordered counter-clockwise: trailing edge -> lower surface -> leading edge
    -> upper surface -> back to the trailing edge (the i-wrap of the O-grid).
    `n_surface` must be even.
    """
    if n_surface % 2 != 0:
        raise ValueError(f"n_surface must be even for a closed O-grid, got {n_surface}")
    m = n_surface // 2 + 1
    upper = naca0012_coordinates(m, chord=chord)  # LE -> TE, y >= 0
    lower = upper.copy()
    lower[:, 1] *= -1.0  # LE -> TE, y <= 0
    te_to_le_lower = lower[::-1]  # TE -> LE along the lower surface (m points)
    le_to_te_upper = upper[1 : m - 1]  # LE -> TE interior of the upper surface
    loop = np.vstack([te_to_le_lower, le_to_te_upper])
    if _signed_area(loop) < 0.0:  # ensure counter-clockwise winding
        loop = loop[::-1]
    return np.asarray(loop, dtype=np.float64)


def airfoil_ogrid(
    *,
    n_surface: int,
    n_normal: int,
    radius_chords: float,
    first_cell_height: float,
    chord: float,
) -> tuple[NDArray[np.float64], list[tuple[int, int, int, int]], list[Marker]]:
    """Build an O-grid around the analytic NACA 0012 profile.

    The i-index wraps the airfoil (periodic); the j-index marches radially out
    to a circular far field, geometrically clustered to `first_cell_height` at
    the wall. Returns `(points, quads, markers)` for `_write_su2`.
    """
    loop = _closed_airfoil_loop(n_surface, chord)
    ni = loop.shape[0]
    nj = n_normal + 1

    centre = np.array([0.5 * chord, 0.0])
    radial = geometric_spacing(n_normal, first_cell_height * chord, radius_chords * chord)
    frac = radial / radial[-1]

    # The far-field point matched to surface point i sits on the circle at the
    # angle of (surface[i] - centre): a transfinite blend that keeps grid lines
    # from crossing for a slender, near-convex section.
    rel = loop - centre
    theta = np.arctan2(rel[:, 1], rel[:, 0])
    circle = centre + radius_chords * chord * np.column_stack([np.cos(theta), np.sin(theta)])

    points = np.empty((ni * nj, 2), dtype=np.float64)
    for i in range(ni):
        for j in range(nj):
            s = frac[j]
            points[i * nj + j] = (1.0 - s) * loop[i] + s * circle[i]

    quads = _structured_quads(ni, nj, periodic_i=True)
    markers: list[Marker] = [
        ("airfoil", _wrap_line(ni, nj, j=0)),
        ("farfield", _wrap_line(ni, nj, j=nj - 1)),
    ]
    return points, quads, markers


def _wrap_line(ni: int, nj: int, *, j: int) -> list[tuple[int, int]]:
    """Boundary line elements along a periodic (wrapping) j-constant edge."""

    def idx(i: int, jj: int) -> int:
        return i * nj + jj

    return [(idx(i, j), idx((i + 1) % ni, j)) for i in range(ni)]


# --- rectangular-topology grids (flat plate, bump) ----------------------------
def _rect_grid(
    x: NDArray[np.float64],
    wall_y: NDArray[np.float64],
    *,
    n_normal: int,
    first_cell_height: float,
    domain_height: float,
) -> tuple[NDArray[np.float64], int, int]:
    """A structured grid over a rectangular topology with a shaped lower wall.

    Column `i` rises from `wall_y[i]` to `wall_y[i] + domain_height` through
    `n_normal` geometrically-clustered cells. Returns `(points, ni, nj)`.
    """
    ni = x.shape[0]
    nj = n_normal + 1
    radial = geometric_spacing(n_normal, first_cell_height, domain_height)
    points = np.empty((ni * nj, 2), dtype=np.float64)
    for i in range(ni):
        for j in range(nj):
            points[i * nj + j] = (x[i], wall_y[i] + radial[j])
    return points, ni, nj


def flat_plate_grid(
    *,
    plate_length: float,
    inlet_length: float,
    domain_height: float,
    n_streamwise: int,
    n_inlet: int,
    n_normal: int,
    first_cell_height: float,
) -> tuple[NDArray[np.float64], list[tuple[int, int, int, int]], list[Marker]]:
    """Build the TMR turbulent flat-plate mesh.

    A sharp leading edge at x=0: the lower boundary is a symmetry plane for
    x < 0 and a no-slip wall for 0 <= x <= `plate_length`. A node lands exactly
    on x=0 so the marker split is exact.
    """
    x_sym = np.linspace(-inlet_length, 0.0, n_inlet + 1)
    x_plate = np.linspace(0.0, plate_length, n_streamwise + 1)[1:]
    x = np.concatenate([x_sym, x_plate])
    wall_y = np.zeros_like(x)
    points, ni, nj = _rect_grid(
        x,
        wall_y,
        n_normal=n_normal,
        first_cell_height=first_cell_height,
        domain_height=domain_height,
    )
    quads = _structured_quads(ni, nj, periodic_i=False)
    bottom = _edge_line(ni, nj, j=0)
    markers: list[Marker] = [
        ("symmetry", bottom[:n_inlet]),
        ("wall", bottom[n_inlet:]),
        ("farfield", _edge_line(ni, nj, j=nj - 1)),
        ("inlet", _edge_line(ni, nj, i=0)),
        ("outlet", _edge_line(ni, nj, i=ni - 1)),
    ]
    return points, quads, markers


def bump_grid(
    *,
    bump_length: float,
    inlet_length: float,
    outlet_length: float,
    domain_height: float,
    bump_height: float,
    n_bump: int,
    n_inlet: int,
    n_outlet: int,
    n_normal: int,
    first_cell_height: float,
) -> tuple[NDArray[np.float64], list[tuple[int, int, int, int]], list[Marker]]:
    """Build the TMR 2D bump-in-channel mesh.

    The lower wall is the analytic bump (`bump_height_at`); it is a no-slip
    wall for 0 <= x <= `bump_length` and a symmetry plane up- and downstream.
    """
    x_in = np.linspace(-inlet_length, 0.0, n_inlet + 1)
    x_bump = np.linspace(0.0, bump_length, n_bump + 1)[1:]
    x_out = np.linspace(bump_length, bump_length + outlet_length, n_outlet + 1)[1:]
    x = np.concatenate([x_in, x_bump, x_out])
    wall_y = bump_height_at(x, height=bump_height)
    points, ni, nj = _rect_grid(
        x,
        wall_y,
        n_normal=n_normal,
        first_cell_height=first_cell_height,
        domain_height=domain_height,
    )
    quads = _structured_quads(ni, nj, periodic_i=False)
    bottom = _edge_line(ni, nj, j=0)
    markers: list[Marker] = [
        ("symmetry", bottom[:n_inlet] + bottom[n_inlet + n_bump :]),
        ("wall", bottom[n_inlet : n_inlet + n_bump]),
        ("farfield", _edge_line(ni, nj, j=nj - 1)),
        ("inlet", _edge_line(ni, nj, i=0)),
        ("outlet", _edge_line(ni, nj, i=ni - 1)),
    ]
    return points, quads, markers


def write_su2_mesh(
    path: Path,
    *,
    points: NDArray[np.float64],
    quads: list[tuple[int, int, int, int]],
    markers: list[Marker],
) -> None:
    """Write a generated structured quad mesh to `path` in native `.su2` format."""
    _write_su2(path, points=points, quads=quads, markers=markers)

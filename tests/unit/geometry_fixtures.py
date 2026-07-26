"""Tiny synthetic surfaces for the aero.geometry unit tests (Stage 18).

Everything is built in-code — no binary fixtures in the repo. The unit cube is the
canonical clean surface (watertight, manifold, outward-consistent winding,
volume exactly 1); the variants each break exactly one quality property.
"""

from __future__ import annotations

import numpy as np
from aero.geometry import TriSurface

CUBE_VERTICES = np.array(
    [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (1.0, 0.0, 1.0),
        (1.0, 1.0, 1.0),
        (0.0, 1.0, 1.0),
    ],
    dtype=np.float64,
)

# Outward winding (CCW seen from outside); signed volume = +1.
CUBE_FACES = np.array(
    [
        (0, 2, 1),
        (0, 3, 2),  # bottom  (z=0)
        (4, 5, 6),
        (4, 6, 7),  # top     (z=1)
        (0, 1, 5),
        (0, 5, 4),  # front   (y=0)
        (2, 3, 7),
        (2, 7, 6),  # back    (y=1)
        (0, 4, 7),
        (0, 7, 3),  # left    (x=0)
        (1, 2, 6),
        (1, 6, 5),  # right   (x=1)
    ],
    dtype=np.int64,
)


def cube() -> TriSurface:
    """Clean closed unit cube."""
    return TriSurface(CUBE_VERTICES, CUBE_FACES)


def cube_with_hole() -> TriSurface:
    """Cube missing one triangle — a 3-edge boundary loop."""
    return TriSurface(CUBE_VERTICES, CUBE_FACES[1:])


def cube_flipped_face() -> TriSurface:
    """Cube with one face wound backwards — inconsistent orientation."""
    faces = CUBE_FACES.copy()
    faces[0] = faces[0][[0, 2, 1]]
    return TriSurface(CUBE_VERTICES, faces)


def cube_inverted() -> TriSurface:
    """Cube with every face wound inward — consistent but negative volume."""
    return TriSurface(CUBE_VERTICES, CUBE_FACES[:, [0, 2, 1]])


def cube_with_fin() -> TriSurface:
    """Cube plus a fin hanging off an existing edge — that edge sees 3 faces."""
    vertices = np.vstack([CUBE_VERTICES, [(0.5, -0.5, 0.5)]])
    faces = np.vstack([CUBE_FACES, [(0, 1, 8)]]).astype(np.int64)
    return TriSurface(vertices, faces)


def cube_with_duplicate_face() -> TriSurface:
    """Cube with one face repeated verbatim."""
    faces = np.vstack([CUBE_FACES, CUBE_FACES[:1]]).astype(np.int64)
    return TriSurface(CUBE_VERTICES, faces)


def crossing_triangles() -> TriSurface:
    """Two triangles piercing each other, sharing no vertex."""
    vertices = np.array(
        [
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (1.0, 2.0, 0.0),  # triangle A in z=0 plane
            (1.0, 0.5, -1.0),
            (1.0, 0.5, 1.0),
            (1.0, 2.5, 0.0),  # triangle B crossing it
        ],
        dtype=np.float64,
    )
    faces = np.array([(0, 1, 2), (3, 4, 5)], dtype=np.int64)
    return TriSurface(vertices, faces)


def separated_triangles() -> TriSurface:
    """Two far-apart triangles — no intersection."""
    vertices = np.array(
        [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (10.0, 10.0, 10.0),
            (11.0, 10.0, 10.0),
            (10.0, 11.0, 10.0),
        ],
        dtype=np.float64,
    )
    faces = np.array([(0, 1, 2), (3, 4, 5)], dtype=np.int64)
    return TriSurface(vertices, faces)


def coplanar_overlapping_triangles() -> TriSurface:
    """Two coplanar triangles overlapping in area, sharing no vertex."""
    vertices = np.array(
        [
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (0.0, 2.0, 0.0),
            (0.5, 0.5, 0.0),
            (2.5, 0.5, 0.0),
            (0.5, 2.5, 0.0),
        ],
        dtype=np.float64,
    )
    faces = np.array([(0, 1, 2), (3, 4, 5)], dtype=np.int64)
    return TriSurface(vertices, faces)


def cube_with_sliver() -> TriSurface:
    """Cube plus one sliver triangle of ~1e-16 area on the top face plane."""
    vertices = np.vstack(
        [CUBE_VERTICES, [(0.2, 0.2, 1.0), (0.8, 0.2, 1.0), (0.5, 0.2 + 1e-15, 1.0)]]
    )
    faces = np.vstack([CUBE_FACES, [(8, 9, 10)]]).astype(np.int64)
    return TriSurface(vertices, faces)


def cube_with_split_seam() -> TriSurface:
    """Cube whose top four vertices are duplicated with a 1e-9 offset for the two
    top faces — near-duplicate vertices leaving the top detached (boundary edges)."""
    offset = np.zeros((4, 3))
    offset[:, 2] = 1e-9
    vertices = np.vstack([CUBE_VERTICES, CUBE_VERTICES[4:8] + offset])
    faces = CUBE_FACES.copy()
    for i in range(4):  # remap the two top faces to the duplicated ring 8..11
        faces[2:4][faces[2:4] == 4 + i] = 8 + i
    return TriSurface(vertices, faces)


def on_plane_edge_triangles() -> TriSurface:
    """Two triangles sharing a real segment, with vertices EXACTLY on each other's
    plane — the Möller zero-distance case (regression: Stage-18 review finding 1)."""
    vertices = np.array(
        [
            (1.0, 4.0, 0.0),
            (1.0, 1.0, 0.0),
            (1.0, 2.0, 1.0),  # triangle A, in the plane x = 1
            (-1.0, -1.0, 0.0),
            (3.0, -1.0, 0.0),
            (1.0, 3.0, 0.0),  # triangle B, in the plane z = 0
        ],
        dtype=np.float64,
    )
    faces = np.array([(0, 1, 2), (3, 4, 5)], dtype=np.int64)
    return TriSurface(vertices, faces)


def single_on_plane_vertex_triangles() -> TriSurface:
    """Triangles crossing with exactly ONE vertex on the other's plane
    (dist = [0, +a, -b]) — the other zero-distance branch."""
    vertices = np.array(
        [
            (0.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (1.0, 2.0, 0.0),  # triangle A in z = 0
            (1.0, 0.5, 0.0),  # exactly on A's plane
            (1.0, 0.5, 1.0),
            (1.0, 2.5, -1.0),
        ],
        dtype=np.float64,
    )
    faces = np.array([(0, 1, 2), (3, 4, 5)], dtype=np.int64)
    return TriSurface(vertices, faces)


def near_coplanar_plates(
    gap: float = 1e-4, extent: float = 8e-3, subdiv: int = 4, scale: float = 1.0
) -> TriSurface:
    """Two parallel, finely tessellated plates separated by `gap` — they never touch.

    Regression for Stage-18 review finding 2: the coplanarity epsilon must be a LENGTH,
    so refining the tessellation (smaller facets) must not manufacture intersections.
    """
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for plate, z in enumerate((0.0, gap)):
        base = len(verts)
        for i in range(subdiv + 1):
            for j in range(subdiv + 1):
                verts.append((extent * i / subdiv, extent * j / subdiv, z))
        stride = subdiv + 1
        for i in range(subdiv):
            for j in range(subdiv):
                a = base + i * stride + j
                b, c, d = a + 1, a + stride, a + stride + 1
                if plate == 0:
                    faces += [(a, b, c), (b, d, c)]
                else:
                    faces += [(a, c, b), (b, c, d)]
    v = np.array(verts, dtype=np.float64) * scale
    return TriSurface(v, np.array(faces, dtype=np.int64))

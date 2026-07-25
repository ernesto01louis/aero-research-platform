"""Core types for arbitrary-geometry ingestion (Stage 18, ADR-033).

PLATFORM-NOT-HUB: stdlib + numpy + pydantic only. The :class:`TriSurface` is the
in-memory unit every loader (STL / 3MF in core, STEP behind ``aero[cad]``) produces and
every quality / repair / meshing consumer takes. It is deliberately *not* a pydantic
model: a surface can carry 10^5+ triangles, so it holds read-only numpy arrays with
shape/dtype/bounds validation in ``__init__`` (the :class:`aero.postprocess._base.Signal`
tuple idiom does not scale to meshes). Everything derived from it that travels in a
bundle (quality reports, repair actions, the ingestion record) IS strict pydantic — see
:mod:`aero.geometry.quality` and :mod:`aero.geometry.ingest`.

Topological *validation* lives in :mod:`aero.geometry.quality`, not here: the
constructor accepts a topologically broken surface on purpose, so the quality gate can
*report* what is wrong instead of dying before the report exists. Only structural
impossibilities (wrong shapes, out-of-range indices, non-finite coordinates) raise at
construction — those make every downstream computation meaningless.
"""

from __future__ import annotations

import numpy as np
from pydantic import ConfigDict

__all__ = ["GeometryError", "TriSurface", "weld_corners"]

# Shared strict config for every pydantic model in aero/geometry — mirrors
# aero/postprocess/_base.py:_STRICT and the fail-loud-pydantic rule.
STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)


class GeometryError(RuntimeError):
    """An external geometry is unusable — malformed file, failed quality gate,
    repair bound exceeded, or an exhausted mesh fallback ladder.

    Raised loud and caught once, at the CLI boundary (exit code 5) — never swallowed
    with a silent repair-and-proceed (the Stage-18 contract). The message always names
    every failed check, so the operator's next action is to inspect the quality report,
    fix or re-export the source geometry, and re-run ``aero geometry ingest``.
    """


class TriSurface:
    """An indexed triangle surface: ``vertices (V, 3) float64``, ``faces (F, 3) int64``.

    Arrays are copied and made read-only, so a ``TriSurface`` is immutable after
    construction (repairs build a *new* surface). Structural validation only — see the
    module docstring for why topological brokenness is allowed through.
    """

    __slots__ = ("_faces", "_vertices")

    def __init__(self, vertices: np.ndarray, faces: np.ndarray) -> None:
        v = np.array(vertices, dtype=np.float64, copy=True)
        f = np.array(faces, dtype=np.int64, copy=True)
        if v.ndim != 2 or v.shape[1] != 3 or v.shape[0] < 3:
            raise GeometryError(f"TriSurface: vertices must be (V>=3, 3), got {v.shape}")
        if f.ndim != 2 or f.shape[1] != 3 or f.shape[0] < 1:
            raise GeometryError(f"TriSurface: faces must be (F>=1, 3), got {f.shape}")
        if not np.isfinite(v).all():
            raise GeometryError("TriSurface: vertices contain non-finite coordinates")
        if f.min() < 0 or f.max() >= v.shape[0]:
            raise GeometryError(
                f"TriSurface: face indices must lie in [0, {v.shape[0]}), "
                f"got [{f.min()}, {f.max()}]"
            )
        v.setflags(write=False)
        f.setflags(write=False)
        self._vertices = v
        self._faces = f

    # ------------------------------------------------------------------ basics

    @property
    def vertices(self) -> np.ndarray:
        """Read-only ``(V, 3) float64`` vertex coordinates."""
        return self._vertices

    @property
    def faces(self) -> np.ndarray:
        """Read-only ``(F, 3) int64`` vertex indices per triangle."""
        return self._faces

    @property
    def n_vertices(self) -> int:
        return int(self._vertices.shape[0])

    @property
    def n_faces(self) -> int:
        return int(self._faces.shape[0])

    @property
    def bbox(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """Axis-aligned bounding box ``(min_xyz, max_xyz)``."""
        lo = self._vertices.min(axis=0)
        hi = self._vertices.max(axis=0)
        return (float(lo[0]), float(lo[1]), float(lo[2])), (
            float(hi[0]),
            float(hi[1]),
            float(hi[2]),
        )

    @property
    def bbox_diagonal(self) -> float:
        """Length of the bounding-box diagonal — the surface's own length scale."""
        lo, hi = self.bbox
        return float(np.linalg.norm(np.asarray(hi) - np.asarray(lo)))

    # ------------------------------------------------------------- derived data

    def triangle_corners(self) -> np.ndarray:
        """``(F, 3, 3)`` corner coordinates per face."""
        return np.asarray(self._vertices[self._faces])

    def face_cross(self) -> np.ndarray:
        """``(F, 3)`` un-normalized face normals ``(b - a) x (c - a)``."""
        tri = self.triangle_corners()
        return np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])

    def face_areas(self) -> np.ndarray:
        """``(F,)`` triangle areas."""
        return np.asarray(0.5 * np.linalg.norm(self.face_cross(), axis=1))

    def area(self) -> float:
        """Total surface area."""
        return float(self.face_areas().sum())

    def signed_volume(self) -> float:
        """Signed enclosed volume (divergence theorem); positive = outward winding.

        Only meaningful on a closed, consistently-oriented surface — the quality gate
        establishes that before anyone reads this as "the volume".
        """
        tri = self.triangle_corners()
        return float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)

    def directed_edges(self) -> np.ndarray:
        """``(3F, 2)`` directed edges, faces' winding preserved (a->b, b->c, c->a)."""
        f = self._faces
        return np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]], axis=0)

    def undirected_edges(self) -> np.ndarray:
        """``(3F, 2)`` edges with each vertex pair sorted (undirected form)."""
        return np.sort(self.directed_edges(), axis=1)

    def edge_lengths(self) -> np.ndarray:
        """``(3F,)`` lengths of all (directed) edges."""
        e = self.directed_edges()
        return np.asarray(np.linalg.norm(self._vertices[e[:, 1]] - self._vertices[e[:, 0]], axis=1))


def weld_corners(corners: np.ndarray) -> TriSurface:
    """Weld a ``(F, 3, 3)`` triangle soup into an indexed surface — **exact** matches only.

    Bitwise-identical coordinate dedup is a lossless representation change every loader
    applies (STL is a soup by definition; OCCT tessellates per-face with duplicated
    boundary nodes) — it is what makes edge-based topology checks meaningful.
    Tolerance-based merging of *nearly*-equal vertices is a declared repair action
    (:mod:`aero.geometry.repair`), never something a loader does silently.
    """
    flat = np.ascontiguousarray(corners.reshape(-1, 3), dtype=np.float64)
    unique, inverse = np.unique(flat.view([("", flat.dtype)] * 3), return_inverse=True)
    vertices = unique.view(flat.dtype).reshape(-1, 3)
    faces = inverse.reshape(-1, 3).astype(np.int64)
    return TriSurface(vertices, faces)

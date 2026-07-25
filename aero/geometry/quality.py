"""Surface-quality analysis for ingested geometry (Stage 18, ADR-033).

Computes the typed :class:`QualityReport` the ingestion gate (Q-gates, ADR-034)
evaluates: watertightness (no boundary edges), edge-manifoldness (no edge on more than
two faces), orientation consistency (every interior edge traversed once per direction),
duplicate faces, degenerate triangles, pairwise self-intersections of non-adjacent
triangles, and the feature-size proxies (min edge length / min triangle altitude) the
mesher's first-cell sizing is checked against.

Self-intersection is exact-arithmetic-free by design: a sweep-and-prune AABB broadphase
followed by a vectorized Möller interval narrow phase, with an epsilon of
``1e-9 * bbox_diagonal``. Configurations *within epsilon of touching* are counted as
intersecting — conservative on purpose: the gate demands cleanly separated geometry,
and a surface that only "almost" self-intersects is exactly the kind that produces a
garbage snappyHexMesh downstream.

All checks assume the loader's exact-weld normalization (identical coordinates share a
vertex index — see :mod:`aero.geometry.stl`), which makes "shares no vertex index" the
correct non-adjacency test.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, Field

from aero.geometry._base import STRICT, TriSurface

__all__ = ["DEGENERATE_AREA_FRACTION", "QualityReport", "compute_quality"]

# A triangle is degenerate when its area is below this fraction of bbox_diagonal^2
# (or when it repeats a vertex index). Pre-registered as part of Q4 (ADR-034).
DEGENERATE_AREA_FRACTION = 1e-12

# Relative epsilon for the plane-distance classification in the intersection test.
_INTERSECT_EPS_FRACTION = 1e-9


class QualityReport(BaseModel):
    """Computed quality of a triangle surface — the input to the ingestion Q-gates.

    ``watertight``/``manifold``/``orientation_consistent`` are derived here (not by the
    caller) so every consumer reads one consistent definition: watertight = zero
    boundary edges; manifold = no edge shared by more than two faces.
    """

    model_config = STRICT

    n_vertices: int = Field(..., ge=3)
    n_faces: int = Field(..., ge=1)
    n_boundary_edges: int = Field(..., ge=0, description="Edges on exactly one face.")
    n_non_manifold_edges: int = Field(..., ge=0, description="Edges on three or more faces.")
    n_duplicate_faces: int = Field(..., ge=0, description="Faces repeating a vertex triple.")
    n_degenerate_faces: int = Field(
        ..., ge=0, description="Faces with a repeated index or near-zero area (Q4)."
    )
    orientation_consistent: bool = Field(
        ..., description="Every directed edge appears at most once (consistent winding)."
    )
    self_intersections_checked: bool = Field(
        ..., description="Whether the pairwise intersection test ran."
    )
    n_intersecting_pairs: int = Field(
        ..., ge=0, description="Non-adjacent triangle pairs that intersect (0 if unchecked)."
    )
    watertight: bool = Field(..., description="No boundary edges (closed surface).")
    manifold: bool = Field(..., description="No non-manifold edges.")
    min_edge_length: float = Field(..., ge=0.0)
    min_altitude: float = Field(
        ..., ge=0.0, description="Min triangle altitude over non-degenerate faces."
    )
    bbox_min: tuple[float, float, float]
    bbox_max: tuple[float, float, float]
    bbox_diagonal: float = Field(..., gt=0.0)
    surface_area: float = Field(..., ge=0.0)
    signed_volume: float = Field(
        ..., description="Signed volume; meaningful only for a closed, oriented surface."
    )


def _degenerate_mask(surface: TriSurface) -> np.ndarray:
    """Faces with a repeated vertex index or area below the declared fraction."""
    f = surface.faces
    repeated = (f[:, 0] == f[:, 1]) | (f[:, 1] == f[:, 2]) | (f[:, 0] == f[:, 2])
    tiny = surface.face_areas() < DEGENERATE_AREA_FRACTION * surface.bbox_diagonal**2
    return np.asarray(repeated | tiny)


def _edge_counts(surface: TriSurface) -> tuple[int, int, bool]:
    """(n_boundary_edges, n_non_manifold_edges, orientation_consistent)."""
    undirected = surface.undirected_edges()
    _, counts = np.unique(undirected, axis=0, return_counts=True)
    n_boundary = int((counts == 1).sum())
    n_non_manifold = int((counts > 2).sum())
    directed = surface.directed_edges()
    _, dcounts = np.unique(directed, axis=0, return_counts=True)
    orientation_consistent = bool((dcounts == 1).all())
    return n_boundary, n_non_manifold, orientation_consistent


def _duplicate_face_count(surface: TriSurface) -> int:
    canonical = np.sort(surface.faces, axis=1)
    unique = np.unique(canonical, axis=0)
    return surface.n_faces - int(unique.shape[0])


def _candidate_pairs(surface: TriSurface, active: np.ndarray) -> np.ndarray:
    """Sweep-and-prune AABB broadphase over the ``active`` (non-degenerate) faces.

    Returns ``(P, 2)`` face-index pairs with overlapping AABBs that share no vertex.
    """
    idx = np.flatnonzero(active)
    tri = surface.triangle_corners()[idx]
    mins = tri.min(axis=1)
    maxs = tri.max(axis=1)
    order = np.argsort(mins[:, 0], kind="stable")
    xmin_sorted = mins[order, 0]
    xmax_sorted = maxs[order, 0]
    faces = surface.faces
    chunks: list[np.ndarray] = []
    for k in range(idx.size):
        end = int(np.searchsorted(xmin_sorted, xmax_sorted[k], side="right"))
        if end <= k + 1:
            continue
        i_local = order[k]
        cand_local = order[k + 1 : end]
        overlap = (
            (mins[cand_local, 1] <= maxs[i_local, 1])
            & (maxs[cand_local, 1] >= mins[i_local, 1])
            & (mins[cand_local, 2] <= maxs[i_local, 2])
            & (maxs[cand_local, 2] >= mins[i_local, 2])
        )
        cand_local = cand_local[overlap]
        if cand_local.size == 0:
            continue
        i_face = idx[i_local]
        cand_face = idx[cand_local]
        shared = (faces[cand_face][:, :, None] == faces[i_face][None, None, :]).any(axis=(1, 2))
        cand_face = cand_face[~shared]
        if cand_face.size:
            chunks.append(
                np.stack([np.full(cand_face.size, i_face, dtype=np.int64), cand_face], axis=1)
            )
    if not chunks:
        return np.empty((0, 2), dtype=np.int64)
    return np.concatenate(chunks, axis=0)


def _interval_on_line(proj: np.ndarray, dist: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Möller interval of a triangle on the plane-intersection line.

    ``proj``: (P, 3) vertex projections onto the line direction; ``dist``: (P, 3)
    signed distances to the *other* triangle's plane (not all one strict sign).
    """
    d0, d1, d2 = dist[:, 0], dist[:, 1], dist[:, 2]
    odd = np.where(d0 * d1 > 0.0, 2, np.where(d0 * d2 > 0.0, 1, 0))
    rows = np.arange(dist.shape[0])
    others = np.stack([(odd + 1) % 3, (odd + 2) % 3], axis=1)
    p_odd = proj[rows, odd][:, None]
    d_odd = dist[rows, odd][:, None]
    p_k = np.take_along_axis(proj, others, axis=1)
    d_k = np.take_along_axis(dist, others, axis=1)
    denom = d_odd - d_k
    frac = np.divide(d_odd, denom, out=np.zeros_like(denom), where=np.abs(denom) > 0.0)
    t = p_odd + (p_k - p_odd) * frac
    return t.min(axis=1), t.max(axis=1)


def _coplanar_overlap(t1: np.ndarray, t2: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """2D separating-axis overlap test for coplanar triangle pairs.

    ``t1``/``t2``: (P, 3, 3) corners; ``normal``: (P, 3) shared plane normal.
    Returns a boolean mask: True where the projected triangles overlap.
    """
    drop = np.abs(normal).argmax(axis=1)
    keep = np.stack([(drop + 1) % 3, (drop + 2) % 3], axis=1)
    p = np.take_along_axis(t1, keep[:, None, :], axis=2)
    q = np.take_along_axis(t2, keep[:, None, :], axis=2)
    overlap = np.ones(t1.shape[0], dtype=bool)
    for tri_a, tri_b in ((p, q), (q, p)):
        for e in range(3):
            edge = tri_a[:, (e + 1) % 3] - tri_a[:, e]
            axis = np.stack([-edge[:, 1], edge[:, 0]], axis=1)
            proj_a = np.einsum("pki,pi->pk", tri_a, axis)
            proj_b = np.einsum("pki,pi->pk", tri_b, axis)
            separated = (proj_a.max(axis=1) < proj_b.min(axis=1)) | (
                proj_b.max(axis=1) < proj_a.min(axis=1)
            )
            overlap &= ~separated
    return overlap


def _count_intersections(surface: TriSurface, active: np.ndarray) -> int:
    """Count non-adjacent intersecting triangle pairs (Möller + SAT coplanar path)."""
    pairs = _candidate_pairs(surface, active)
    if pairs.shape[0] == 0:
        return 0
    eps = _INTERSECT_EPS_FRACTION * surface.bbox_diagonal
    tri = surface.triangle_corners()
    t1 = tri[pairs[:, 0]]
    t2 = tri[pairs[:, 1]]
    n1 = np.cross(t1[:, 1] - t1[:, 0], t1[:, 2] - t1[:, 0])
    n2 = np.cross(t2[:, 1] - t2[:, 0], t2[:, 2] - t2[:, 0])
    d1 = np.einsum("pki,pi->pk", t1 - t2[:, 0:1], n2)  # T1 verts vs T2 plane
    d2 = np.einsum("pki,pi->pk", t2 - t1[:, 0:1], n1)  # T2 verts vs T1 plane

    strict_apart_1 = (d1 > eps).all(axis=1) | (d1 < -eps).all(axis=1)
    strict_apart_2 = (d2 > eps).all(axis=1) | (d2 < -eps).all(axis=1)
    maybe = ~(strict_apart_1 | strict_apart_2)
    coplanar = maybe & (np.abs(d1) <= eps).all(axis=1) & (np.abs(d2) <= eps).all(axis=1)
    crossing = maybe & ~coplanar

    count = 0
    if crossing.any():
        line = np.cross(n1[crossing], n2[crossing])
        axis = np.abs(line).argmax(axis=1)
        sel = axis[:, None, None]
        proj1 = np.take_along_axis(t1[crossing], sel, axis=2).squeeze(2)
        proj2 = np.take_along_axis(t2[crossing], sel, axis=2).squeeze(2)
        lo1, hi1 = _interval_on_line(proj1, d1[crossing])
        lo2, hi2 = _interval_on_line(proj2, d2[crossing])
        count += int(((hi1 >= lo2 - eps) & (hi2 >= lo1 - eps)).sum())
    if coplanar.any():
        count += int(_coplanar_overlap(t1[coplanar], t2[coplanar], n1[coplanar]).sum())
    return count


def compute_quality(surface: TriSurface, *, check_self_intersections: bool = True) -> QualityReport:
    """Compute the full :class:`QualityReport` for a surface.

    ``check_self_intersections=False`` skips the (only) super-linear check; the report
    records the skip so a gate that requires the check fails loud instead of silently
    passing an unchecked surface.
    """
    degenerate = _degenerate_mask(surface)
    n_boundary, n_non_manifold, orientation_ok = _edge_counts(surface)
    edge_lengths = surface.edge_lengths()
    areas = surface.face_areas()
    ok_faces = ~degenerate
    if ok_faces.any():
        # Altitude = 2*area / longest edge of the face.
        per_face_edges = edge_lengths.reshape(3, -1).T[ok_faces]
        min_altitude = float((2.0 * areas[ok_faces] / per_face_edges.max(axis=1)).min())
    else:
        min_altitude = 0.0
    n_intersecting = _count_intersections(surface, ok_faces) if check_self_intersections else 0
    lo, hi = surface.bbox
    return QualityReport(
        n_vertices=surface.n_vertices,
        n_faces=surface.n_faces,
        n_boundary_edges=n_boundary,
        n_non_manifold_edges=n_non_manifold,
        n_duplicate_faces=_duplicate_face_count(surface),
        n_degenerate_faces=int(degenerate.sum()),
        orientation_consistent=orientation_ok,
        self_intersections_checked=check_self_intersections,
        n_intersecting_pairs=n_intersecting,
        watertight=n_boundary == 0,
        manifold=n_non_manifold == 0,
        min_edge_length=float(edge_lengths.min()),
        min_altitude=min_altitude,
        bbox_min=lo,
        bbox_max=hi,
        bbox_diagonal=surface.bbox_diagonal,
        surface_area=float(areas.sum()),
        signed_volume=surface.signed_volume(),
    )

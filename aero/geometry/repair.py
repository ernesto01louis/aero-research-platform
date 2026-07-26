"""Bounded, declared surface repair (Stage 18, ADR-033).

Every mutation is a typed :class:`RepairAction` in the returned ledger — a repaired
geometry is auditable, and the ingestion record shows exactly what changed (the
Stage-18 contract: never a silent repair-and-proceed). The bounds are pre-registered
(R-gates, ADR-034): tolerance-merging is capped at a declared fraction of the bounding
-box diagonal, hole filling at a declared edge count per hole and hole count per
surface. Anything outside the bounds is left untouched — the post-repair quality gate
then fails loud with the residual defects in the report.

What repair NEVER does: move a vertex by more than the merge tolerance, invent
geometry beyond planar patches over small holes, or touch a surface region the ledger
does not record. Unfillable holes (too large, too many, non-manifold boundary, or a
degenerate ring the ear-clipper cannot triangulate) are simply left open.

Vertex compaction (dropping vertices no face references after merges/drops) is a
lossless re-indexing, performed on every rebuild and not ledgered.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from aero.geometry._base import STRICT, TriSurface
from aero.geometry.quality import DEGENERATE_AREA_FRACTION

__all__ = ["RepairAction", "RepairConfig", "repair"]


class RepairAction(BaseModel):
    """One declared repair mutation, recorded in the ingestion ledger."""

    model_config = STRICT

    kind: Literal[
        "merge_vertices",
        "drop_duplicate_faces",
        "drop_degenerate_faces",
        "fix_winding",
        "flip_global_orientation",
        "fill_hole",
    ]
    count: int = Field(..., ge=1, description="Entities affected (vertices/faces/flips/edges).")
    detail: str = Field(..., min_length=1)


class RepairConfig(BaseModel):
    """Pre-registered repair bounds (R-gates, ADR-034)."""

    model_config = STRICT

    merge_tolerance_fraction: float = Field(
        default=1e-6,
        gt=0.0,
        lt=1e-3,
        description="Vertex-merge tolerance as a fraction of the bbox diagonal.",
    )
    max_hole_edges: int = Field(
        default=32, ge=3, description="Largest boundary loop the planar patcher may fill."
    )
    max_holes: int = Field(default=8, ge=0, description="Most holes a single repair pass may fill.")


def _rebuild(vertices: np.ndarray, faces: np.ndarray) -> TriSurface:
    """Compact to referenced vertices and construct a fresh surface."""
    used, inverse = np.unique(faces.ravel(), return_inverse=True)
    return TriSurface(vertices[used], inverse.reshape(-1, 3))


def _merge_vertices(
    surface: TriSurface, tolerance: float
) -> tuple[TriSurface, RepairAction | None]:
    """Grid-quantized tolerance merge (declared limitation: pairs straddling a grid
    boundary at distance < tolerance may survive; the post-repair gate arbitrates)."""
    quantized = np.round(surface.vertices / tolerance).astype(np.int64)
    _, first, inverse = np.unique(quantized, axis=0, return_index=True, return_inverse=True)
    n_merged = surface.n_vertices - int(first.size)
    if n_merged == 0:
        return surface, None
    new_vertices = surface.vertices[first]
    new_faces = inverse[surface.faces]
    action = RepairAction(
        kind="merge_vertices",
        count=n_merged,
        detail=f"merged {n_merged} vertices within tolerance {tolerance:.3e} (grid quantization)",
    )
    return _rebuild(new_vertices, new_faces), action


def _drop_duplicate_faces(surface: TriSurface) -> tuple[TriSurface, RepairAction | None]:
    canonical = np.sort(surface.faces, axis=1)
    _, first = np.unique(canonical, axis=0, return_index=True)
    n_dropped = surface.n_faces - int(first.size)
    if n_dropped == 0:
        return surface, None
    keep = np.sort(first)
    action = RepairAction(
        kind="drop_duplicate_faces",
        count=n_dropped,
        detail=f"dropped {n_dropped} faces repeating an existing vertex triple",
    )
    return _rebuild(surface.vertices.copy(), surface.faces[keep]), action


def _drop_degenerate_faces(surface: TriSurface) -> tuple[TriSurface, RepairAction | None]:
    f = surface.faces
    repeated = (f[:, 0] == f[:, 1]) | (f[:, 1] == f[:, 2]) | (f[:, 0] == f[:, 2])
    tiny = surface.face_areas() < DEGENERATE_AREA_FRACTION * surface.bbox_diagonal**2
    drop = repeated | tiny
    n_dropped = int(drop.sum())
    if n_dropped == 0:
        return surface, None
    if bool(drop.all()):
        # Nothing left to rebuild from — leave untouched; the gate reports it.
        return surface, None
    action = RepairAction(
        kind="drop_degenerate_faces",
        count=n_dropped,
        detail=f"dropped {n_dropped} degenerate faces (repeated index or near-zero area)",
    )
    return _rebuild(surface.vertices.copy(), surface.faces[~drop]), action


def _fix_winding(surface: TriSurface) -> tuple[TriSurface, tuple[RepairAction, ...]]:
    """BFS-orient faces consistently, then flip globally if the volume is negative.

    Preconditions (checked here, silently skipped otherwise — the gate reports the
    underlying defect): edge-manifold surface. Runs only when orientation is broken
    or (for closed surfaces) the winding is inward.
    """
    undirected = surface.undirected_edges()
    edges_unique, edge_inverse, counts = np.unique(
        undirected, axis=0, return_inverse=True, return_counts=True
    )
    if (counts > 2).any():
        return surface, ()
    directed = surface.directed_edges()
    _, dcounts = np.unique(directed, axis=0, return_counts=True)
    needs_bfs = bool((dcounts > 1).any())

    flips = np.zeros(surface.n_faces, dtype=bool)
    if needs_bfs:
        n_faces = surface.n_faces
        face_of_edge = np.tile(np.arange(n_faces, dtype=np.int64), 3)
        # For every undirected edge with two incident faces, note both faces and
        # whether each traverses it "forward" (as sorted) or "backward".
        forward = (directed[:, 0] < directed[:, 1]).astype(np.int8)
        order = np.argsort(edge_inverse, kind="stable")
        eids = edge_inverse[order]
        starts = np.searchsorted(eids, np.arange(edges_unique.shape[0]))
        adjacency: list[list[tuple[int, int]]] = [[] for _ in range(n_faces)]
        for e in range(edges_unique.shape[0]):
            if counts[e] != 2:
                continue
            a, b = order[starts[e]], order[starts[e] + 1]
            fa, fb = int(face_of_edge[a]), int(face_of_edge[b])
            same_dir = int(forward[a] == forward[b])  # same direction => one must flip
            adjacency[fa].append((fb, same_dir))
            adjacency[fb].append((fa, same_dir))
        visited = np.zeros(n_faces, dtype=bool)
        for seed in range(n_faces):
            if visited[seed]:
                continue
            visited[seed] = True
            stack = [seed]
            while stack:
                current = stack.pop()
                for neighbor, same_dir in adjacency[current]:
                    if visited[neighbor]:
                        continue
                    visited[neighbor] = True
                    flips[neighbor] = flips[current] ^ bool(same_dir)
                    stack.append(neighbor)

    faces = surface.faces.copy()
    actions: list[RepairAction] = []
    n_flipped = int(flips.sum())
    if n_flipped:
        faces[flips] = faces[flips][:, [0, 2, 1]]
        actions.append(
            RepairAction(
                kind="fix_winding",
                count=n_flipped,
                detail=f"flipped {n_flipped} faces to a consistent winding (BFS over edges)",
            )
        )
    candidate = TriSurface(surface.vertices.copy(), faces) if n_flipped else surface
    # Outward global orientation only decidable for a closed surface.
    boundary_free = not bool((counts == 1).any())
    if boundary_free and candidate.signed_volume() < 0.0:
        faces_flipped = candidate.faces.copy()[:, [0, 2, 1]]
        actions.append(
            RepairAction(
                kind="flip_global_orientation",
                count=candidate.n_faces,
                detail="flipped all faces: signed volume was negative (inward winding)",
            )
        )
        candidate = TriSurface(candidate.vertices.copy(), faces_flipped)
    return candidate, tuple(actions)


def _boundary_loops(surface: TriSurface) -> list[list[int]] | None:
    """Chain boundary edges into closed vertex loops (walk order = face winding).

    Returns None when the boundary is non-manifold (a vertex with more than one
    outgoing boundary edge) — such holes are not fillable here.
    """
    undirected = surface.undirected_edges()
    _, inverse, counts = np.unique(undirected, axis=0, return_inverse=True, return_counts=True)
    boundary_mask = counts[inverse] == 1
    boundary_directed = surface.directed_edges()[boundary_mask]
    if boundary_directed.shape[0] == 0:
        return []
    starts = boundary_directed[:, 0]
    if np.unique(starts).size != starts.size:
        return None
    successor = dict(zip(starts.tolist(), boundary_directed[:, 1].tolist(), strict=True))
    loops: list[list[int]] = []
    remaining = set(successor)
    while remaining:
        v0 = next(iter(remaining))
        loop = [v0]
        remaining.discard(v0)
        v = successor[v0]
        while v != v0:
            if v not in remaining:
                return None  # open chain / crossing boundary — not fillable
            loop.append(v)
            remaining.discard(v)
            v = successor[v]
        loops.append(loop)
    return loops


def _ear_clip(points2d: np.ndarray) -> list[tuple[int, int, int]] | None:
    """Ear-clip a simple 2D polygon (CCW); returns triangle index triples or None."""
    n = points2d.shape[0]
    if n < 3:
        return None
    indices = list(range(n))
    triangles: list[tuple[int, int, int]] = []

    def cross(o: int, a: int, b: int) -> float:
        oa = points2d[a] - points2d[o]
        ob = points2d[b] - points2d[o]
        return float(oa[0] * ob[1] - oa[1] * ob[0])

    guard = 0
    while len(indices) > 3 and guard < 10 * n:
        guard += 1
        clipped = False
        for k in range(len(indices)):
            prev_i = indices[k - 1]
            cur_i = indices[k]
            next_i = indices[(k + 1) % len(indices)]
            if cross(prev_i, cur_i, next_i) <= 0.0:
                continue  # reflex or degenerate corner
            ear = True
            tri = points2d[[prev_i, cur_i, next_i]]
            for other in indices:
                if other in (prev_i, cur_i, next_i):
                    continue
                p = points2d[other]
                s1 = (tri[1, 0] - tri[0, 0]) * (p[1] - tri[0, 1]) - (tri[1, 1] - tri[0, 1]) * (
                    p[0] - tri[0, 0]
                )
                s2 = (tri[2, 0] - tri[1, 0]) * (p[1] - tri[1, 1]) - (tri[2, 1] - tri[1, 1]) * (
                    p[0] - tri[1, 0]
                )
                s3 = (tri[0, 0] - tri[2, 0]) * (p[1] - tri[2, 1]) - (tri[0, 1] - tri[2, 1]) * (
                    p[0] - tri[2, 0]
                )
                if s1 >= 0.0 and s2 >= 0.0 and s3 >= 0.0:
                    ear = False
                    break
            if ear:
                triangles.append((prev_i, cur_i, next_i))
                indices.pop(k)
                clipped = True
                break
        if not clipped:
            return None
    if len(indices) == 3:
        triangles.append((indices[0], indices[1], indices[2]))
    return triangles


def _fill_holes(
    surface: TriSurface, config: RepairConfig
) -> tuple[TriSurface, tuple[RepairAction, ...]]:
    loops = _boundary_loops(surface)
    if loops is None or not loops:
        return surface, ()
    actions: list[RepairAction] = []
    new_faces: list[np.ndarray] = []
    filled = 0
    for loop in loops:
        if filled >= config.max_holes or len(loop) > config.max_hole_edges:
            continue
        pts = surface.vertices[np.asarray(loop, dtype=np.int64)]
        centroid = pts.mean(axis=0)
        centered = pts - centroid
        # Best-fit plane via SVD; the two leading right-singular vectors span it.
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
        # The boundary walk follows existing face winding; the patch must traverse
        # each boundary edge in reverse, i.e. triangulate the REVERSED loop.
        reversed_loop = loop[::-1]
        pts2d = (surface.vertices[np.asarray(reversed_loop)] - centroid) @ vt[:2].T
        # Ear clipping needs CCW orientation in the projection plane.
        signed_area = float(
            np.sum(pts2d[:, 0] * np.roll(pts2d[:, 1], -1) - np.roll(pts2d[:, 0], -1) * pts2d[:, 1])
            / 2.0
        )
        if signed_area < 0.0:
            # Mirror so the ear-convexity tests see a CCW polygon. The emitted
            # triples follow the polygon traversal order either way, so the 3D
            # winding (fixed by the reversed-loop order) is unaffected.
            pts2d = pts2d[:, ::-1]
        triangles = _ear_clip(pts2d)
        if triangles is None:
            continue
        loop_arr = np.asarray(reversed_loop, dtype=np.int64)
        tri_idx = np.asarray(triangles, dtype=np.int64)
        new_faces.append(loop_arr[tri_idx])
        filled += 1
        actions.append(
            RepairAction(
                kind="fill_hole",
                count=len(loop),
                detail=f"filled a {len(loop)}-edge boundary loop with a planar ear-clip patch",
            )
        )
    if not new_faces:
        return surface, ()
    faces = np.concatenate([surface.faces, *new_faces], axis=0)
    return TriSurface(surface.vertices.copy(), faces), tuple(actions)


def repair(
    surface: TriSurface, config: RepairConfig | None = None
) -> tuple[TriSurface, tuple[RepairAction, ...]]:
    """Run the bounded repair pipeline; returns the new surface + the action ledger.

    Order matters and is fixed: merge -> drop duplicates -> drop degenerate ->
    fix winding -> fill holes (patches inherit the now-consistent winding).
    """
    cfg = config or RepairConfig()
    ledger: list[RepairAction] = []
    tolerance = cfg.merge_tolerance_fraction * surface.bbox_diagonal

    surface, action = _merge_vertices(surface, tolerance)
    if action:
        ledger.append(action)
    surface, action = _drop_duplicate_faces(surface)
    if action:
        ledger.append(action)
    surface, action = _drop_degenerate_faces(surface)
    if action:
        ledger.append(action)
    surface, winding_actions = _fix_winding(surface)
    ledger.extend(winding_actions)
    surface, hole_actions = _fill_holes(surface, cfg)
    ledger.extend(hole_actions)
    return surface, tuple(ledger)

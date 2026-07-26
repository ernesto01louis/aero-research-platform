"""STEP loading via the CAD kernel behind ``aero[cad]`` (Stage 18, ADR-033).

Every function lazy-imports ``build123d`` (Apache-2.0, atop the OCP wheel wrapping
OCCT, LGPL-2.1-with-exception — license disposition in ADR-033) so importing this
module stays clean on a base install; the actionable ImportError names the extra.
Pattern: :mod:`aero.surrogates.domino.model`.

Tessellation is a *declared* transformation: the linear/angular deflection used is
returned alongside the surface so the ingestion record can carry it — a STEP solid
tessellated at a different deflection is a different discrete geometry.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from aero.geometry._base import GeometryError, TriSurface, weld_corners

__all__ = ["DEFAULT_ANGULAR_DEFLECTION_DEG", "DEFAULT_LINEAR_DEFLECTION", "load_step"]

# Declared tessellation defaults (recorded by callers; ADR-033).
DEFAULT_LINEAR_DEFLECTION = 1e-3
DEFAULT_ANGULAR_DEFLECTION_DEG = 15.0


def load_step(
    path: Path,
    *,
    linear_deflection: float = DEFAULT_LINEAR_DEFLECTION,
    angular_deflection_deg: float = DEFAULT_ANGULAR_DEFLECTION_DEG,
) -> TriSurface:
    """Import a STEP file and tessellate it into a :class:`TriSurface`.

    ``linear_deflection`` is absolute (model units); ``angular_deflection_deg`` bounds
    the facet-normal deviation on curved faces.
    """
    try:
        from build123d import import_step  # lazy: aero[cad]
    except ImportError as exc:  # pragma: no cover — CAD-extra-gated
        raise ImportError(
            "STEP ingestion needs the CAD kernel: pip install 'aero[cad]' (ADR-033)"
        ) from exc

    try:
        shape = import_step(str(path))
    except Exception as exc:
        raise GeometryError(f"{path}: STEP import failed: {exc}") from exc

    try:
        vertices_faces = shape.tessellate(
            tolerance=linear_deflection,
            angular_tolerance=np.deg2rad(angular_deflection_deg),
        )
    except Exception as exc:
        raise GeometryError(f"{path}: STEP tessellation failed: {exc}") from exc
    raw_vertices, raw_faces = vertices_faces
    if not raw_faces:
        raise GeometryError(f"{path}: STEP tessellation produced no triangles")
    vertices = np.array([(v.X, v.Y, v.Z) for v in raw_vertices], dtype=np.float64)
    faces = np.array(raw_faces, dtype=np.int64)
    # OCCT tessellates per B-rep face with duplicated boundary nodes; the exact weld
    # (see weld_corners) restores shared topology so edge checks are meaningful.
    return weld_corners(vertices[faces])

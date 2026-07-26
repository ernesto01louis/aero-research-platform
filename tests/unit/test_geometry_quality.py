"""aero.geometry — TriSurface structural checks + QualityReport correctness.

Each fixture surface breaks exactly one quality property; the report must localize
it. Pure numpy + pydantic — runs in the required CI unit job (Stage 18, ADR-033).
"""

from __future__ import annotations

import numpy as np
import pytest
from aero.geometry import GeometryError, TriSurface, compute_quality

from tests.unit.geometry_fixtures import (
    CUBE_FACES,
    CUBE_VERTICES,
    coplanar_overlapping_triangles,
    crossing_triangles,
    cube,
    cube_flipped_face,
    cube_with_duplicate_face,
    cube_with_fin,
    cube_with_hole,
    cube_with_sliver,
    separated_triangles,
)

# --- TriSurface structural validation --------------------------------------------


def test_trisurface_rejects_bad_shapes() -> None:
    with pytest.raises(GeometryError, match="vertices must be"):
        TriSurface(np.zeros((2, 3)), CUBE_FACES)
    with pytest.raises(GeometryError, match="faces must be"):
        TriSurface(CUBE_VERTICES, np.zeros((0, 3), dtype=np.int64))


def test_trisurface_rejects_out_of_range_indices() -> None:
    faces = CUBE_FACES.copy()
    faces[0, 0] = 99
    with pytest.raises(GeometryError, match="face indices"):
        TriSurface(CUBE_VERTICES, faces)


def test_trisurface_rejects_non_finite() -> None:
    vertices = CUBE_VERTICES.copy()
    vertices[0, 0] = np.nan
    with pytest.raises(GeometryError, match="non-finite"):
        TriSurface(vertices, CUBE_FACES)


def test_trisurface_is_immutable() -> None:
    surf = cube()
    with pytest.raises(ValueError, match="read-only"):
        surf.vertices[0, 0] = 5.0


def test_cube_derived_quantities() -> None:
    surf = cube()
    assert surf.n_vertices == 8
    assert surf.n_faces == 12
    assert surf.area() == pytest.approx(6.0)
    assert surf.signed_volume() == pytest.approx(1.0)
    assert surf.bbox_diagonal == pytest.approx(np.sqrt(3.0))


# --- QualityReport per-property localization -------------------------------------


def test_clean_cube_report_is_all_green() -> None:
    report = compute_quality(cube())
    assert report.watertight
    assert report.manifold
    assert report.orientation_consistent
    assert report.n_boundary_edges == 0
    assert report.n_duplicate_faces == 0
    assert report.n_degenerate_faces == 0
    assert report.n_intersecting_pairs == 0
    assert report.self_intersections_checked
    assert report.signed_volume == pytest.approx(1.0)
    assert report.min_edge_length == pytest.approx(1.0)


def test_hole_shows_as_boundary_edges() -> None:
    report = compute_quality(cube_with_hole())
    assert not report.watertight
    assert report.n_boundary_edges == 3
    assert report.manifold  # a hole is not a manifoldness defect


def test_fin_shows_as_non_manifold_edge() -> None:
    report = compute_quality(cube_with_fin())
    assert not report.manifold
    assert report.n_non_manifold_edges == 1


def test_flipped_face_breaks_orientation_only() -> None:
    report = compute_quality(cube_flipped_face())
    assert not report.orientation_consistent
    assert report.watertight  # undirected topology is still closed


def test_duplicate_face_is_counted() -> None:
    report = compute_quality(cube_with_duplicate_face())
    assert report.n_duplicate_faces == 1


def test_sliver_is_degenerate() -> None:
    report = compute_quality(cube_with_sliver())
    assert report.n_degenerate_faces == 1


# --- self-intersection -----------------------------------------------------------


def test_crossing_triangles_intersect() -> None:
    report = compute_quality(crossing_triangles())
    assert report.n_intersecting_pairs == 1


def test_separated_triangles_do_not_intersect() -> None:
    report = compute_quality(separated_triangles())
    assert report.n_intersecting_pairs == 0


def test_coplanar_overlap_counts_as_intersection() -> None:
    report = compute_quality(coplanar_overlapping_triangles())
    assert report.n_intersecting_pairs == 1


def test_adjacent_faces_never_count_as_intersecting() -> None:
    # The cube's faces touch along shared edges everywhere; none may count.
    report = compute_quality(cube())
    assert report.n_intersecting_pairs == 0


def test_intersection_check_can_be_skipped_but_is_recorded() -> None:
    report = compute_quality(crossing_triangles(), check_self_intersections=False)
    assert not report.self_intersections_checked
    assert report.n_intersecting_pairs == 0


# --- regressions: Stage-18 adversarial review (self-intersection false neg/pos) ------


def test_on_plane_edge_intersection_is_detected() -> None:
    """Vertices exactly on the other triangle's plane must not collapse the interval."""
    from tests.unit.geometry_fixtures import on_plane_edge_triangles

    assert compute_quality(on_plane_edge_triangles()).n_intersecting_pairs == 1


def test_single_on_plane_vertex_intersection_is_detected() -> None:
    from tests.unit.geometry_fixtures import single_on_plane_vertex_triangles

    assert compute_quality(single_on_plane_vertex_triangles()).n_intersecting_pairs == 1


@pytest.mark.parametrize("rot_a", [0, 1, 2])
@pytest.mark.parametrize("rot_b", [0, 1, 2])
def test_intersection_count_is_corner_order_invariant(rot_a: int, rot_b: int) -> None:
    """The property that structurally forbids the odd-vertex class of bug: rotating a
    face's corners is the same geometry, so the verdict may not change."""
    from tests.unit.geometry_fixtures import on_plane_edge_triangles

    surf = on_plane_edge_triangles()
    faces = surf.faces.copy()
    faces[0] = np.roll(faces[0], rot_a)
    faces[1] = np.roll(faces[1], rot_b)
    rotated = TriSurface(surf.vertices, faces)
    assert compute_quality(rotated).n_intersecting_pairs == 1


@pytest.mark.parametrize("subdiv", [1, 2, 4, 8])
def test_close_but_separated_plates_never_intersect(subdiv: int) -> None:
    """The coplanarity window is a length (1e-9 * bbox_diag), NOT 1/area: refining the
    tessellation alone must not manufacture intersections."""
    from tests.unit.geometry_fixtures import near_coplanar_plates

    surf = near_coplanar_plates(gap=1e-4, extent=8e-3, subdiv=subdiv)
    assert compute_quality(surf).n_intersecting_pairs == 0


@pytest.mark.parametrize("scale", [1e-3, 1.0, 1e3])
def test_intersection_classification_is_scale_invariant(scale: float) -> None:
    from tests.unit.geometry_fixtures import near_coplanar_plates

    surf = near_coplanar_plates(gap=1e-4, extent=8e-3, subdiv=8, scale=scale)
    assert compute_quality(surf).n_intersecting_pairs == 0

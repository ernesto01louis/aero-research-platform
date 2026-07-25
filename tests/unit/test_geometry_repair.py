"""aero.geometry.repair — bounded declared repair: actions ledgered, bounds honored.

Every repair must (a) fix what it claims, (b) record a RepairAction, and (c) leave
anything outside its declared bounds untouched. Stage 18, ADR-033/034 (R-gates).
"""

from __future__ import annotations

import pytest
from aero.geometry import RepairConfig, compute_quality, repair

from tests.unit.geometry_fixtures import (
    cube,
    cube_flipped_face,
    cube_inverted,
    cube_with_duplicate_face,
    cube_with_hole,
    cube_with_sliver,
    cube_with_split_seam,
)


def test_clean_cube_repair_is_a_ledgered_noop() -> None:
    repaired, actions = repair(cube())
    assert actions == ()
    assert compute_quality(repaired).watertight


def test_split_seam_merges_and_closes() -> None:
    surf = cube_with_split_seam()
    assert not compute_quality(surf).watertight  # detached top: boundary edges
    repaired, actions = repair(surf)
    kinds = [a.kind for a in actions]
    assert "merge_vertices" in kinds
    report = compute_quality(repaired)
    assert report.watertight
    assert report.n_vertices == 8


def test_hole_is_filled_within_bounds_with_correct_winding() -> None:
    repaired, actions = repair(cube_with_hole())
    assert [a.kind for a in actions] == ["fill_hole"]
    assert actions[0].count == 3
    report = compute_quality(repaired)
    assert report.watertight
    assert report.orientation_consistent
    assert report.signed_volume == pytest.approx(1.0)  # patch wound outward


def test_hole_beyond_declared_bounds_is_left_open() -> None:
    # max_holes=0 forbids filling entirely; the hole must survive, unledgered.
    repaired, actions = repair(cube_with_hole(), RepairConfig(max_holes=0))
    assert actions == ()
    assert not compute_quality(repaired).watertight


def test_flipped_face_is_rewound_consistently() -> None:
    repaired, actions = repair(cube_flipped_face())
    kinds = [a.kind for a in actions]
    assert "fix_winding" in kinds
    report = compute_quality(repaired)
    assert report.orientation_consistent
    assert report.signed_volume == pytest.approx(1.0)


def test_inverted_cube_is_flipped_outward() -> None:
    repaired, actions = repair(cube_inverted())
    assert [a.kind for a in actions] == ["flip_global_orientation"]
    assert compute_quality(repaired).signed_volume == pytest.approx(1.0)


def test_duplicate_face_is_dropped() -> None:
    repaired, actions = repair(cube_with_duplicate_face())
    assert [a.kind for a in actions] == ["drop_duplicate_faces"]
    assert repaired.n_faces == 12


def test_sliver_is_dropped() -> None:
    repaired, actions = repair(cube_with_sliver())
    assert any(a.kind == "drop_degenerate_faces" for a in actions)
    assert compute_quality(repaired).n_degenerate_faces == 0


def test_repair_config_bounds_are_validated() -> None:
    with pytest.raises(Exception, match=r"merge_tolerance_fraction|less than"):
        RepairConfig(merge_tolerance_fraction=0.5)

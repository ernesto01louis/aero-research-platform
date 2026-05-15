"""Contract tests for the periodic-strip flat-plate mesh writer."""

from __future__ import annotations

import re
from pathlib import Path

from aero_research_platform.meshing.periodic_riblet_strip import (
    FlatPlateRibletMeshSpec,
    write_all,
    write_block_mesh_dict,
    write_block_mesh_dict_structured,
    write_mesh_quality_dict,
    write_riblet_stl,
    write_snappy_hex_mesh_dict,
)


def test_default_spec_meets_stage5_brief_minimums() -> None:
    spec = FlatPlateRibletMeshSpec()
    # Stage-5 brief: ≥ 4 pitches spanwise, ≥ 16 cells per pitch.
    assert spec.n_pitches_spanwise >= 4
    assert spec.n_y_per_pitch >= 16
    # y+ < 1 budget — same as Stage 4.
    assert spec.first_layer_thickness <= 1e-6
    # Default to riblet ON — explicit toggle is the smooth-baseline path.
    assert spec.riblet_enabled is True
    # Bechert canonical aspect ratios.
    assert spec.h_over_s == 0.5
    assert spec.t_over_s == 0.02
    # Drag-integration window is downstream of inlet by ≥ 2c so BL is developed.
    assert spec.meas_window_x_start >= 1.5
    assert spec.meas_window_x_end > spec.meas_window_x_start


def test_spanwise_extent_property_matches_n_times_pitch() -> None:
    spec = FlatPlateRibletMeshSpec(pitch_s=0.005, n_pitches_spanwise=6)
    assert spec.spanwise_extent == 0.030


def test_block_mesh_dict_has_cyclic_pair(tmp_path: Path) -> None:
    spec = FlatPlateRibletMeshSpec()
    out = tmp_path / "blockMeshDict"
    write_block_mesh_dict(spec, out)
    text = out.read_text()
    # Cyclic patches paired by neighbourPatch.
    assert "frontPeriodic" in text
    assert "backPeriodic" in text
    assert "type cyclic" in text
    assert "neighbourPatch backPeriodic" in text
    assert "neighbourPatch frontPeriodic" in text


def test_block_mesh_dict_has_inlet_outlet_top_bottom(tmp_path: Path) -> None:
    spec = FlatPlateRibletMeshSpec()
    out = tmp_path / "blockMeshDict"
    write_block_mesh_dict(spec, out)
    text = out.read_text()
    for patch in ("inlet", "outlet", "top", "bottomWall"):
        assert patch in text, f"missing patch '{patch}'"
    # bottomWall is a wall patch (so OpenFOAM applies wall functions).
    assert "type wall" in text


def test_block_mesh_dict_cell_counts_round_trip(tmp_path: Path) -> None:
    spec = FlatPlateRibletMeshSpec(n_x=200, n_y_per_pitch=20, n_pitches_spanwise=4, n_z=60)
    out = tmp_path / "blockMeshDict"
    write_block_mesh_dict(spec, out)
    text = out.read_text()
    # n_y in the hex block is n_pitches_spanwise * n_y_per_pitch.
    assert f"( {spec.n_x} {spec.n_pitches_spanwise * spec.n_y_per_pitch} {spec.n_z} )" in text


def test_riblet_stl_facet_count_matches_strip_segments(tmp_path: Path) -> None:
    spec = FlatPlateRibletMeshSpec(n_pitches_spanwise=3)
    out = tmp_path / "riblets.stl"
    write_riblet_stl(spec, out)
    text = out.read_text()
    assert text.startswith("solid riblets")
    assert text.rstrip().endswith("endsolid riblets")
    n_facets = len(re.findall(r"facet normal", text))
    # blade_strip_profile yields 5n + 1 points → 5n segments → 10n triangles.
    assert n_facets == 10 * spec.n_pitches_spanwise


def test_snappy_dict_omits_geometry_when_riblet_disabled(tmp_path: Path) -> None:
    spec = FlatPlateRibletMeshSpec(riblet_enabled=False)
    out = tmp_path / "snappyHexMeshDict"
    write_snappy_hex_mesh_dict(spec, out)
    text = out.read_text()
    assert "castellatedMesh false" in text
    assert "snap            false" in text
    assert "addLayers       true" in text
    # No STL reference in geometry block.
    assert "riblets.stl" not in text
    # Layers still applied — on the bottomWall patch directly, for matched
    # wall resolution against the riblet baseline.
    assert "bottomWall" in text
    assert f"nSurfaceLayers {spec.n_layers}" in text


def test_snappy_dict_references_stl_when_riblet_enabled(tmp_path: Path) -> None:
    spec = FlatPlateRibletMeshSpec(riblet_enabled=True)
    out = tmp_path / "snappyHexMeshDict"
    write_snappy_hex_mesh_dict(spec, out)
    text = out.read_text()
    assert "castellatedMesh true" in text
    assert "riblets.stl" in text
    assert f"level ( {spec.surface_refinement_min} {spec.surface_refinement_max} )" in text
    assert f"nSurfaceLayers {spec.n_layers}" in text


def test_mesh_quality_dict_inherits_stage4_thresholds(tmp_path: Path) -> None:
    out = tmp_path / "meshQualityDict"
    write_mesh_quality_dict(out)
    text = out.read_text()
    # Same tuning that proved SA-stable in Stage 4.
    assert "maxNonOrtho         70" in text
    assert "maxConcave          60" in text
    assert "minDeterminant      1e-5" in text


def test_write_all_riblet_emits_structured_blockmesh_only(tmp_path: Path) -> None:
    """Riblet case: structured multi-block blockMeshDict + meshQualityDict only.

    No STL, no snappyHexMeshDict — the blade geometry is baked into the
    block topology. This is the post-pilot-v3 architecture change after
    snappy + STL + addLayers produced 28k negative-volume cells.
    """
    spec = FlatPlateRibletMeshSpec(riblet_enabled=True, n_pitches_spanwise=2)
    paths = write_all(spec, tmp_path)
    assert (tmp_path / "system" / "blockMeshDict").exists()
    assert (tmp_path / "system" / "meshQualityDict").exists()
    assert not (tmp_path / "constant" / "triSurface" / "riblets.stl").exists()
    assert not (tmp_path / "system" / "snappyHexMeshDict").exists()
    assert set(paths) == {"blockMeshDict", "meshQualityDict"}


def test_write_all_smooth_keeps_snappy_path(tmp_path: Path) -> None:
    """Smooth baseline still uses single-block blockMesh + snappy + addLayers."""
    spec = FlatPlateRibletMeshSpec(riblet_enabled=False)
    paths = write_all(spec, tmp_path)
    assert not (tmp_path / "constant" / "triSurface" / "riblets.stl").exists()
    assert (tmp_path / "system" / "blockMeshDict").exists()
    assert (tmp_path / "system" / "snappyHexMeshDict").exists()
    assert "stl" not in paths
    assert set(paths) == {"blockMeshDict", "snappyHexMeshDict", "meshQualityDict"}


def test_structured_dict_has_n_blocks_8_times_n_pitches(tmp_path: Path) -> None:
    """8 blocks per pitch period: 2 groove + 3 BL-band + 3 freestream."""
    spec = FlatPlateRibletMeshSpec(riblet_enabled=True, n_pitches_spanwise=4)
    out = tmp_path / "blockMeshDict"
    write_block_mesh_dict_structured(spec, out)
    text = out.read_text()
    hex_lines = [line for line in text.splitlines() if line.strip().startswith("hex (")]
    assert len(hex_lines) == 8 * spec.n_pitches_spanwise


def test_structured_dict_has_riblet_patch(tmp_path: Path) -> None:
    """blade walls + tip form a `riblets` wall patch (no STL needed)."""
    spec = FlatPlateRibletMeshSpec(riblet_enabled=True, n_pitches_spanwise=2)
    out = tmp_path / "blockMeshDict"
    write_block_mesh_dict_structured(spec, out)
    text = out.read_text()
    assert "riblets" in text
    # Three riblet faces per period: two side walls + one tip.
    # Look at the riblets patch faces block specifically.
    riblets_section = text.split("riblets")[1].split("frontPeriodic")[0]
    riblet_face_lines = [
        line for line in riblets_section.splitlines()
        if re.match(r"\s*\( \d+ \d+ \d+ \d+ \)", line)
    ]
    assert len(riblet_face_lines) == 3 * spec.n_pitches_spanwise


def test_structured_dict_has_cyclic_pair(tmp_path: Path) -> None:
    spec = FlatPlateRibletMeshSpec(riblet_enabled=True)
    out = tmp_path / "blockMeshDict"
    write_block_mesh_dict_structured(spec, out)
    text = out.read_text()
    assert "frontPeriodic" in text
    assert "backPeriodic" in text
    assert "neighbourPatch backPeriodic" in text
    assert "neighbourPatch frontPeriodic" in text


def test_structured_dict_is_periodic_channel(tmp_path: Path) -> None:
    """Periodic channel: cyclic x pair, symmetryPlane top, no inlet/outlet."""
    spec = FlatPlateRibletMeshSpec(riblet_enabled=True)
    out = tmp_path / "blockMeshDict"
    write_block_mesh_dict_structured(spec, out)
    text = out.read_text()
    # streamwise cyclic pair (replaces inlet/outlet)
    assert "xMinCyclic" in text
    assert "xMaxCyclic" in text
    assert "neighbourPatch xMaxCyclic" in text
    assert "neighbourPatch xMinCyclic" in text
    # channel centreline is a symmetry plane, not a freestream patch
    assert "type symmetryPlane" in text
    # no developing-BL inlet/outlet patches
    assert "inlet" not in text
    assert "outlet" not in text


def test_structured_dict_vertex_count(tmp_path: Path) -> None:
    """2 x_slabs * (1 + 3*n_p) y_cols * 4 z_rows total vertices.

    Four z-rows: 0, h, z_bl, Lz (three z-bands).
    """
    spec = FlatPlateRibletMeshSpec(riblet_enabled=True, n_pitches_spanwise=4)
    out = tmp_path / "blockMeshDict"
    write_block_mesh_dict_structured(spec, out)
    text = out.read_text()
    vertex_lines = [
        line for line in text.splitlines()
        if re.match(r"\s*\( -?\d.*-?\d.*-?\d.*\)\s*//\s*\d", line)
    ]
    expected = 2 * (1 + 3 * spec.n_pitches_spanwise) * 4
    assert len(vertex_lines) == expected


def test_structured_dict_rejects_smooth_spec() -> None:
    """Structured writer is riblet-only; smooth case has no blade geometry."""
    spec = FlatPlateRibletMeshSpec(riblet_enabled=False)
    try:
        write_block_mesh_dict_structured(spec, Path("/tmp/_unused"))
    except RuntimeError as e:
        assert "riblet_enabled" in str(e).lower()
    else:
        raise AssertionError("expected RuntimeError")

"""Contract tests for the periodic-strip flat-plate mesh writer."""

from __future__ import annotations

import re
from pathlib import Path

from aero_research_platform.meshing.periodic_riblet_strip import (
    FlatPlateRibletMeshSpec,
    write_all,
    write_block_mesh_dict,
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


def test_write_all_riblet_emits_full_tree(tmp_path: Path) -> None:
    spec = FlatPlateRibletMeshSpec(riblet_enabled=True, n_pitches_spanwise=2)
    paths = write_all(spec, tmp_path)
    assert (tmp_path / "constant" / "triSurface" / "riblets.stl").exists()
    assert (tmp_path / "system" / "blockMeshDict").exists()
    assert (tmp_path / "system" / "snappyHexMeshDict").exists()
    assert (tmp_path / "system" / "meshQualityDict").exists()
    assert set(paths) == {"stl", "blockMeshDict", "snappyHexMeshDict", "meshQualityDict"}


def test_write_all_smooth_omits_stl(tmp_path: Path) -> None:
    spec = FlatPlateRibletMeshSpec(riblet_enabled=False)
    paths = write_all(spec, tmp_path)
    assert not (tmp_path / "constant" / "triSurface" / "riblets.stl").exists()
    assert (tmp_path / "system" / "blockMeshDict").exists()
    assert (tmp_path / "system" / "snappyHexMeshDict").exists()
    assert "stl" not in paths
    assert set(paths) == {"blockMeshDict", "snappyHexMeshDict", "meshQualityDict"}

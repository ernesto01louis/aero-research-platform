"""Contract tests for the streamwise-periodic channel mesh writer.

See STAGE-5-REDESIGN.md — the riblet domain is a periodic channel,
not a developing-BL plate. Both the riblet (structured multi-block)
and smooth (single-block) writers emit pure blockMeshDicts; no
snappyHexMesh, no STL.
"""

from __future__ import annotations

import re
from pathlib import Path

from aero_research_platform.meshing.periodic_riblet_strip import (
    FlatPlateRibletMeshSpec,
    write_all,
    write_block_mesh_dict,
    write_block_mesh_dict_structured,
    write_mesh_quality_dict,
)


def test_default_spec_meets_stage5_brief_minimums() -> None:
    spec = FlatPlateRibletMeshSpec()
    # Stage-5 brief: ≥ 4 pitches spanwise, ≥ 16 cells per pitch.
    assert spec.n_pitches_spanwise >= 4
    assert spec.n_y_per_pitch >= 16
    # Default to riblet ON — explicit toggle is the smooth-baseline path.
    assert spec.riblet_enabled is True
    # Bechert canonical aspect ratios.
    assert spec.h_over_s == 0.5
    assert spec.t_over_s == 0.02
    # Periodic channel: friction Reynolds number is set.
    assert spec.re_tau > 0


def test_spanwise_extent_property_matches_n_times_pitch() -> None:
    spec = FlatPlateRibletMeshSpec(pitch_s=0.005, n_pitches_spanwise=6)
    assert spec.spanwise_extent == 0.030


# ── smooth-baseline single-block periodic channel ────────────────────

def test_smooth_block_mesh_dict_has_cyclic_pairs(tmp_path: Path) -> None:
    spec = FlatPlateRibletMeshSpec(riblet_enabled=False)
    out = tmp_path / "blockMeshDict"
    write_block_mesh_dict(spec, out)
    text = out.read_text()
    # streamwise + spanwise cyclic pairs
    for patch in ("xMinCyclic", "xMaxCyclic", "frontPeriodic", "backPeriodic"):
        assert patch in text, f"missing patch '{patch}'"
    assert "neighbourPatch xMaxCyclic" in text
    assert "neighbourPatch backPeriodic" in text


def test_smooth_block_mesh_dict_channel_patches(tmp_path: Path) -> None:
    """Smooth periodic channel: symmetryPlane top, wall bottom, no inlet/outlet."""
    spec = FlatPlateRibletMeshSpec(riblet_enabled=False)
    out = tmp_path / "blockMeshDict"
    write_block_mesh_dict(spec, out)
    text = out.read_text()
    assert "type symmetryPlane" in text
    assert "bottomWall" in text
    assert "type wall" in text
    assert "inlet" not in text
    assert "outlet" not in text


def test_smooth_block_mesh_dict_cell_counts(tmp_path: Path) -> None:
    spec = FlatPlateRibletMeshSpec(riblet_enabled=False, n_x=200, n_y_per_pitch=20,
                                   n_pitches_spanwise=4)
    out = tmp_path / "blockMeshDict"
    write_block_mesh_dict(spec, out)
    text = out.read_text()
    n_y = spec.n_pitches_spanwise * spec.n_y_per_pitch
    n_z = spec.n_z_groove + spec.n_z_bl + spec.n_z_outer
    assert f"( {spec.n_x} {n_y} {n_z} )" in text


def test_mesh_quality_dict_inherits_stage4_thresholds(tmp_path: Path) -> None:
    out = tmp_path / "meshQualityDict"
    write_mesh_quality_dict(out)
    text = out.read_text()
    assert "maxNonOrtho         70" in text
    assert "maxConcave          60" in text
    assert "minDeterminant      1e-5" in text


# ── write_all dispatch ───────────────────────────────────────────────

def test_write_all_riblet_emits_structured_blockmesh_only(tmp_path: Path) -> None:
    """Riblet case: structured multi-block blockMeshDict + meshQualityDict only."""
    spec = FlatPlateRibletMeshSpec(riblet_enabled=True, n_pitches_spanwise=2)
    paths = write_all(spec, tmp_path)
    assert (tmp_path / "system" / "blockMeshDict").exists()
    assert (tmp_path / "system" / "meshQualityDict").exists()
    assert not (tmp_path / "system" / "snappyHexMeshDict").exists()
    assert set(paths) == {"blockMeshDict", "meshQualityDict"}


def test_write_all_smooth_emits_single_block(tmp_path: Path) -> None:
    """Smooth baseline: single-block periodic-channel blockMeshDict."""
    spec = FlatPlateRibletMeshSpec(riblet_enabled=False, n_pitches_spanwise=2)
    paths = write_all(spec, tmp_path)
    assert (tmp_path / "system" / "blockMeshDict").exists()
    assert (tmp_path / "system" / "meshQualityDict").exists()
    assert not (tmp_path / "system" / "snappyHexMeshDict").exists()
    assert set(paths) == {"blockMeshDict", "meshQualityDict"}
    # one hex block for the smooth channel
    text = (tmp_path / "system" / "blockMeshDict").read_text()
    hex_lines = [ln for ln in text.splitlines() if ln.strip().startswith("hex (")]
    assert len(hex_lines) == 1


# ── riblet structured multi-block ────────────────────────────────────

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
    assert "xMinCyclic" in text
    assert "xMaxCyclic" in text
    assert "neighbourPatch xMaxCyclic" in text
    assert "neighbourPatch xMinCyclic" in text
    assert "type symmetryPlane" in text
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

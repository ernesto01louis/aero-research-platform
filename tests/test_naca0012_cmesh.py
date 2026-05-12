"""Mesh-generator contract tests.

The mesh stack writes pure-text OpenFOAM dicts (blockMeshDict,
snappyHexMeshDict, meshQualityDict) and an ASCII STL of the airfoil.
All four writers are unit-testable without OpenFOAM installed — the
tests below verify each one produces a non-empty file with the expected
markers. The live mesh actually built by ``blockMesh`` + ``snappyHexMesh``
runs on the aero LXC during Stage 4 launch.
"""

from __future__ import annotations

import re
from pathlib import Path

from aero_research_platform.meshing.airfoil_cmesh import (
    MeshSpec,
    write_airfoil_stl,
    write_all,
    write_block_mesh_dict,
    write_mesh_quality_dict,
    write_snappy_hex_mesh_dict,
)


def test_default_spec_targets_nasa_tmr_family_ii() -> None:
    spec = MeshSpec()
    assert spec.farfield_radius == 500.0
    assert spec.n_airfoil_per_side == 257
    assert spec.first_layer_thickness <= 1e-6  # y+ < 1 at Re=6e6
    assert spec.n_layers >= 25
    assert spec.expected_cells_lower_bound >= 100_000


def test_surface_refinement_range_sane() -> None:
    spec = MeshSpec()
    assert spec.surface_refinement_min <= spec.surface_refinement_max
    assert spec.surface_refinement_max >= 5


def test_write_airfoil_stl_produces_valid_ascii(tmp_path: Path) -> None:
    spec = MeshSpec(n_airfoil_per_side=33)
    out = tmp_path / "airfoil.stl"
    write_airfoil_stl(spec, out)
    text = out.read_text()
    assert text.startswith("solid airfoil")
    assert text.rstrip().endswith("endsolid airfoil")
    # Each airfoil point contributes 2 triangles (one in z, one out of z).
    # The closed loop has 2*n_per_side-1 distinct points, but we skip the
    # duplicated endpoint, so triangles = 2 * (2*n_per_side - 1).
    n_facets = len(re.findall(r"facet normal", text))
    assert n_facets == 2 * (2 * spec.n_airfoil_per_side - 1)


def test_write_block_mesh_dict_has_8_vertices_and_one_hex(tmp_path: Path) -> None:
    spec = MeshSpec()
    out = tmp_path / "blockMeshDict"
    write_block_mesh_dict(spec, out)
    text = out.read_text()
    assert "blocks" in text
    assert "hex (0 1 2 3 4 5 6 7)" in text
    assert f"( {spec.n_x} {spec.n_y} {spec.n_z} )" in text
    # 8 vertex lines — three space-separated numbers in parens, ending // N.
    n_vertex_lines = sum(
        1 for line in text.splitlines()
        if re.match(r"\s*\( -?\d.*-?\d.*-?\d.*\)\s*//\s*\d", line)
    )
    assert n_vertex_lines == 8
    # Must declare an empty patch for the front/back faces (2D-equivalent).
    assert "type empty" in text


def test_write_snappy_hex_mesh_dict_refinement_and_layers(tmp_path: Path) -> None:
    spec = MeshSpec()
    out = tmp_path / "snappyHexMeshDict"
    write_snappy_hex_mesh_dict(spec, out)
    text = out.read_text()
    assert "castellatedMesh true" in text
    assert "snap            true" in text
    assert "addLayers       true" in text
    # Surface refinement range and layer count must round-trip.
    assert f"level ( {spec.surface_refinement_min} {spec.surface_refinement_max} )" in text
    assert f"nSurfaceLayers {spec.n_layers}" in text
    assert f"firstLayerThickness {spec.first_layer_thickness}" in text
    # Refinement box level.
    assert f"( 1.0 {spec.refinement_box_level} )" in text


def test_write_mesh_quality_dict_has_safe_thresholds(tmp_path: Path) -> None:
    out = tmp_path / "meshQualityDict"
    write_mesh_quality_dict(out)
    text = out.read_text()
    assert "maxNonOrtho         65" in text
    assert "maxInternalSkewness 4" in text


def test_write_all_lays_down_full_tree(tmp_path: Path) -> None:
    spec = MeshSpec(n_airfoil_per_side=33)
    paths = write_all(spec, tmp_path)
    assert (tmp_path / "constant" / "triSurface" / "airfoil.stl").exists()
    assert (tmp_path / "system" / "blockMeshDict").exists()
    assert (tmp_path / "system" / "snappyHexMeshDict").exists()
    assert (tmp_path / "system" / "meshQualityDict").exists()
    assert set(paths) == {"stl", "blockMeshDict", "snappyHexMeshDict", "meshQualityDict"}


def test_first_layer_thickness_yields_yplus_under_one() -> None:
    """First-layer height + Re=6e6 + Schlichting flat-plate y+ heuristic.

    For a flat plate with Cf~0.058*Re^-0.2 and uTau = sqrt(0.5*rho*U^2*Cf),
    a first-cell wall distance of 1e-6 c on NACA 0012 at Re=6e6 gives
    y+~0.3-0.6 over the chord — well below 1.
    """
    spec = MeshSpec()
    Re = 6.0e6
    cf = 0.058 * Re**-0.2
    nu = 1.0 / Re  # non-dim (c, U_inf)
    u_tau = (0.5 * cf) ** 0.5  # U_tau / U_inf
    y_plus = spec.first_layer_thickness * u_tau / nu
    assert y_plus < 1.0, f"y+={y_plus:.3f} exceeds the wall-resolved budget"

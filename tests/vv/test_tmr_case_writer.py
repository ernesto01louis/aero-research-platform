"""Stage 05 unit tests for the OpenFOAM case writers — pure, no cluster.

Covers the airfoil C-grid rebuild and the new TMR flat-plate / 2D-bump writers:
block counts, patch names, surface-sampling function objects, and the
geometry-discriminator round-trip. A bad mesh topology is far cheaper to catch
here than after a cluster solve.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.openfoam.case_writer import write_case
from aero.adapters.openfoam.schemas import CaseSpec
from aero.adapters.openfoam.tmr_case_writer import write_tmr_case
from aero.adapters.openfoam.tmr_geometry import bump_height_at
from aero.adapters.openfoam.tmr_specs import Bump2DSpec, FlatPlateSpec

pytestmark = pytest.mark.stage_05


# --- airfoil C-grid -----------------------------------------------------------
def test_airfoil_cgrid_has_eight_blocks(tmp_path: Path) -> None:
    write_case(CaseSpec(name="naca0012", reynolds=6.0e6, mach=0.15, aoa_deg=0.0), tmp_path)
    bm = (tmp_path / "system" / "blockMeshDict").read_text(encoding="utf-8")
    assert bm.count("hex (") == 8
    assert bm.count("polyLine") == 8  # 4 surface halves x 2 z-planes
    assert "arc " not in bm
    for patch in ("airfoil", "farfield", "front", "back"):
        assert patch in bm


def test_airfoil_cgrid_vertex_count_is_32(tmp_path: Path) -> None:
    write_case(CaseSpec(name="naca0012", reynolds=6.0e6, mach=0.15, aoa_deg=0.0), tmp_path)
    bm = (tmp_path / "system" / "blockMeshDict").read_text(encoding="utf-8")
    verts = bm.split("vertices\n(\n", 1)[1].split("\n);", 1)[0]
    assert verts.count("(") == 32


# --- flat plate ---------------------------------------------------------------
def test_flat_plate_two_blocks_and_patches(tmp_path: Path) -> None:
    write_tmr_case(FlatPlateSpec(name="flat_plate_te", reynolds=5.0e6, mach=0.2), tmp_path)
    bm = (tmp_path / "system" / "blockMeshDict").read_text(encoding="utf-8")
    assert bm.count("hex (") == 2
    for patch in ("wall", "symmetry", "farfield", "front", "back"):
        assert patch in bm
    assert "type symmetryPlane;" in bm


def test_flat_plate_samples_wall_shear_stress(tmp_path: Path) -> None:
    write_tmr_case(FlatPlateSpec(name="flat_plate_te", reynolds=5.0e6, mach=0.2), tmp_path)
    cd = (tmp_path / "system" / "controlDict").read_text(encoding="utf-8")
    assert "wallShearStress" in cd
    assert "surfaceFormat   raw;" in cd
    assert "application     simpleFoam;" in cd


# --- 2D bump ------------------------------------------------------------------
def test_bump_three_blocks_and_curved_wall(tmp_path: Path) -> None:
    write_tmr_case(Bump2DSpec(name="bump_2d", reynolds=3.0e6, mach=0.2), tmp_path)
    bm = (tmp_path / "system" / "blockMeshDict").read_text(encoding="utf-8")
    assert bm.count("hex (") == 3
    assert bm.count("polyLine") == 2  # curved lower wall, both z-planes
    for patch in ("wall", "topSym", "farfield"):
        assert patch in bm


def test_bump_geometry_is_tangent_and_peaks_at_height() -> None:
    # The TMR bump: zero (tangent) at the ends, peak `height` at mid-length.
    assert bump_height_at([0.0])[0] == pytest.approx(0.0)
    assert bump_height_at([1.5])[0] == pytest.approx(0.0)
    assert bump_height_at([0.75])[0] == pytest.approx(0.05)
    assert bump_height_at([-1.0])[0] == 0.0  # flat outside the bump


def test_tmr_specs_are_strict_and_frozen() -> None:
    spec = FlatPlateSpec(name="fp", reynolds=5.0e6, mach=0.2)
    with pytest.raises(Exception):  # noqa: B017 — frozen model rejects assignment
        spec.reynolds = 1.0  # type: ignore[misc]
    with pytest.raises(Exception):  # noqa: B017 — extra='forbid'
        FlatPlateSpec(name="fp", reynolds=5.0e6, mach=0.2, bogus=1)  # type: ignore[call-arg]


def test_tmr_field_files_cover_every_patch(tmp_path: Path) -> None:
    write_tmr_case(Bump2DSpec(name="bump_2d", reynolds=3.0e6, mach=0.2), tmp_path)
    u = (tmp_path / "0" / "U").read_text(encoding="utf-8")
    for patch in ("wall", "topSym", "farfield", "front", "back"):
        assert patch in u

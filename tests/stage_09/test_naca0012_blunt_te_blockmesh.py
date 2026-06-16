"""Stage 09 — NACA 0012 blunt-TE C-grid (ADR-012, V&V hardening).

Host-side STRUCTURAL tests for the blunt-TE blockMeshDict: that the sharp-TE
path is byte-for-byte unchanged (back-compat), and that the blunt path splits
the singular TE vertex, adds the base-wake wedge block, and grows the vertex
count. The blockMesh *validity* + the <3% Cd are confirmed on the Phase-3
cluster mesh-sweep — the tests/vv/test_tmr_naca0012.py xfail stays until then.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aero.adapters.openfoam.case_writer import write_case
from aero.adapters.openfoam.geometry import naca0012_coordinates
from aero.adapters.openfoam.schemas import CaseSpec

pytestmark = pytest.mark.stage_09


def _spec(**kw: Any) -> CaseSpec:
    base: dict[str, Any] = {"name": "naca0012", "reynolds": 6.0e6, "mach": 0.15, "aoa_deg": 0.0}
    base.update(kw)
    return CaseSpec(**base)


def _blockmesh(tmp_path: Path, spec: CaseSpec) -> str:
    write_case(spec, tmp_path)
    return (tmp_path / "system" / "blockMeshDict").read_text(encoding="utf-8")


def _vertex_count(text: str) -> int:
    vsec = text.split("vertices", 1)[1].split("blocks", 1)[0]
    return sum(1 for ln in vsec.splitlines() if ln.startswith("    ("))


def test_sharp_te_is_unchanged_eight_block_cgrid(tmp_path: Path) -> None:
    text = _blockmesh(tmp_path, _spec())  # default = sharp TE
    assert text.count("hex (") == 8
    assert text.count("polyLine") == 8
    assert _vertex_count(text) == 32  # 16 base x 2 span


def test_blunt_te_adds_base_block_and_split_vertex(tmp_path: Path) -> None:
    text = _blockmesh(tmp_path, _spec(trailing_edge_thickness=0.0025, n_te=8))
    # 9 hex blocks: the 8-block C-grid + the base-wake block.
    assert text.count("hex (") == 9
    # 38 vertices (19 base x 2): the lower TE corner 3l plus the split outlet
    # 5u/5l (Stage-10: the outlet split replaces the degenerate collapsed prism).
    assert _vertex_count(text) == 38
    # Surface polyLines are unchanged (the base is a straight line, not a curve).
    assert text.count("polyLine") == 8


def test_blunt_te_base_is_its_own_patch(tmp_path: Path) -> None:
    # Stage-10: the blunt base is a SEPARATE wall patch so it can carry an
    # all-y+ wall function; the sharp TE has no such patch.
    blunt = _blockmesh(tmp_path / "b", _spec(trailing_edge_thickness=0.0025, n_te=8))
    sharp = _blockmesh(tmp_path / "s", _spec())
    assert "airfoil_te" in blunt
    assert "airfoil_te" not in sharp


def test_blunt_base_wake_block_is_non_degenerate(tmp_path: Path) -> None:
    # Stage-10: the base-wake block must be a proper quad — no repeated vertex
    # (the old `hex (te_lo 5 5 3 ...)` collapsed prism produced a zero-area face
    # + 1e150 skewness that failed checkMesh). Assert the last hex block (BW) has
    # four distinct base-face vertices.
    text = _blockmesh(tmp_path, _spec(trailing_edge_thickness=0.0025, n_te=8))
    bw = [ln for ln in text.splitlines() if ln.strip().startswith("hex (")][-1]
    verts = bw.split("hex (", 1)[1].split(")", 1)[0].split()
    base_face = verts[:4]  # v0 v1 v2 v3
    assert len(set(base_face)) == 4, f"BW base face has a repeated vertex (collapsed): {base_face}"


def test_blunt_te_thickness_must_match_geometry() -> None:
    # FAIL-LOUD: trailing_edge_thickness records the FIXED open-TE geometry; a
    # value inconsistent with it (not a free knob) is rejected.
    with pytest.raises(ValueError, match="inconsistent"):
        _spec(trailing_edge_thickness=0.01, n_te=8)


def test_sharp_and_blunt_blockmeshdicts_differ(tmp_path: Path) -> None:
    sharp = _blockmesh(tmp_path / "s", _spec())
    blunt = _blockmesh(tmp_path / "b", _spec(trailing_edge_thickness=0.0025, n_te=8))
    assert sharp != blunt


def test_blunt_geometry_has_finite_te_thickness() -> None:
    closed = naca0012_coordinates(201, blunt_te=False)
    blunt = naca0012_coordinates(201, blunt_te=True)
    assert closed[-1, 1] == 0.0  # sharp closes the TE to a point
    assert blunt[-1, 1] > 0.0  # blunt leaves a finite half-thickness
    assert blunt[-1, 1] == pytest.approx(0.00126, abs=3e-4)  # ~0.0025c full


def test_blunt_te_requires_base_cells() -> None:
    # The fail-loud validator: a blunt TE without base cells is rejected.
    with pytest.raises(ValueError, match="n_te"):
        _spec(trailing_edge_thickness=0.0025, n_te=0)

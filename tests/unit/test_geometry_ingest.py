"""aero.geometry.ingest — the gate raises loud, the record carries everything.

Stage 18, ADR-033: gate failures name every failed Q-check and the repairs already
applied; the IngestedGeometry record serializes without the in-memory surface and
carries the source SHA-256 the provenance config_hash embeds.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from aero.geometry import (
    GeometryError,
    IngestConfig,
    QualityGateConfig,
    RepairConfig,
    ingest,
    write_stl,
)

from tests.unit.geometry_fixtures import cube, cube_with_hole


def _stl(tmp_path: Path, name: str, surf: object) -> Path:
    path = tmp_path / name
    write_stl(surf, path)  # type: ignore[arg-type]
    return path


def test_clean_cube_ingests_with_empty_ledger(tmp_path: Path) -> None:
    path = _stl(tmp_path, "cube.stl", cube())
    record = ingest(path)
    assert record.fmt == "stl"
    assert record.repairs == ()
    assert record.quality.watertight
    assert record.surface_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert record.n_vertices == 8
    assert record.surface.n_faces == 12


def test_broken_geometry_fails_loud_without_repair(tmp_path: Path) -> None:
    path = _stl(tmp_path, "hole.stl", cube_with_hole())
    with pytest.raises(GeometryError, match=r"Q1 not watertight.*repair disabled"):
        ingest(path)


def test_broken_geometry_passes_with_declared_repair(tmp_path: Path) -> None:
    path = _stl(tmp_path, "hole.stl", cube_with_hole())
    record = ingest(path, config=IngestConfig(repair=RepairConfig()))
    assert [a.kind for a in record.repairs] == ["fill_hole"]
    assert record.quality.watertight


def test_gate_failure_after_repair_names_repairs_applied(tmp_path: Path) -> None:
    path = _stl(tmp_path, "hole.stl", cube_with_hole())
    # Forbid hole filling: repair runs (no-op), the gate still fails, and the
    # message shows nothing was silently patched.
    cfg = IngestConfig(repair=RepairConfig(max_holes=0))
    with pytest.raises(GeometryError, match=r"Q1 not watertight.*no repairs applied"):
        ingest(path, config=cfg)


def test_min_feature_size_gate(tmp_path: Path) -> None:
    path = _stl(tmp_path, "cube.stl", cube())
    cfg = IngestConfig(gate=QualityGateConfig(min_feature_size=2.0))
    with pytest.raises(GeometryError, match="Q5 feature size"):
        ingest(path, config=cfg)


def test_skipped_intersection_check_fails_the_gate_that_requires_it(
    tmp_path: Path,
) -> None:
    path = _stl(tmp_path, "cube.stl", cube())
    cfg = IngestConfig(check_self_intersections=False)
    with pytest.raises(GeometryError, match="Q3 self-intersection check did not run"):
        ingest(path, config=cfg)


def test_unsupported_format_fails_loud(tmp_path: Path) -> None:
    path = tmp_path / "cube.obj"
    path.write_text("o cube\n")
    with pytest.raises(GeometryError, match="unsupported geometry format"):
        ingest(path)


def test_missing_file_fails_loud(tmp_path: Path) -> None:
    with pytest.raises(GeometryError, match="does not exist"):
        ingest(tmp_path / "nope.stl")


def test_record_serializes_without_surface(tmp_path: Path) -> None:
    path = _stl(tmp_path, "cube.stl", cube())
    record = ingest(path)
    dumped = record.model_dump(mode="json")
    assert "surface" not in dumped
    assert dumped["quality"]["watertight"] is True
    assert dumped["surface_sha256"] == record.surface_sha256

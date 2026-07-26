"""aero.geometry — STL round-trips, malformed-file fail-loud, minimal 3MF reading.

Stage 18, ADR-033. All fixture files are built in tmp_path — no binaries in the repo.
"""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import pytest
from aero.geometry import GeometryError, compute_quality, read_3mf, read_stl, write_stl

from tests.unit.geometry_fixtures import CUBE_FACES, CUBE_VERTICES, cube

# --- STL -------------------------------------------------------------------------


def test_binary_stl_round_trip_welds_back_to_cube(tmp_path: Path) -> None:
    path = tmp_path / "cube.stl"
    write_stl(cube(), path, binary=True)
    surf = read_stl(path)
    assert surf.n_vertices == 8  # soup welded back to shared vertices
    assert surf.n_faces == 12
    report = compute_quality(surf)
    assert report.watertight
    assert report.signed_volume == pytest.approx(1.0)


def test_ascii_stl_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "cube_ascii.stl"
    write_stl(cube(), path, binary=False)
    surf = read_stl(path)
    assert surf.n_vertices == 8
    assert surf.n_faces == 12


def test_garbage_file_fails_loud(tmp_path: Path) -> None:
    path = tmp_path / "junk.stl"
    path.write_bytes(b"this is not an stl file, not even close, but it is long enough" * 3)
    with pytest.raises(GeometryError, match="not a parseable STL"):
        read_stl(path)


def test_truncated_binary_stl_fails_loud(tmp_path: Path) -> None:
    path = tmp_path / "cube.stl"
    write_stl(cube(), path, binary=True)
    data = path.read_bytes()
    truncated = tmp_path / "truncated.stl"
    truncated.write_bytes(data[:-25])
    with pytest.raises(GeometryError):
        read_stl(truncated)


def test_tiny_file_fails_loud(tmp_path: Path) -> None:
    path = tmp_path / "tiny.stl"
    path.write_bytes(b"solid")
    with pytest.raises(GeometryError, match="too small"):
        read_stl(path)


def test_binary_stl_with_zero_facets_fails_loud(tmp_path: Path) -> None:
    path = tmp_path / "empty.stl"
    path.write_bytes(b"\0" * 80 + struct.pack("<I", 0))
    with pytest.raises(GeometryError):
        read_stl(path)


# --- 3MF -------------------------------------------------------------------------

_RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
    'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
    "</Relationships>"
)


def _model_xml(*, n_objects: int = 1, transform: str | None = None) -> str:
    verts = "".join(f'<vertex x="{x}" y="{y}" z="{z}"/>' for x, y, z in CUBE_VERTICES.tolist())
    tris = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in CUBE_FACES.tolist())
    obj = (
        '<object id="{oid}" type="model"><mesh>'
        f"<vertices>{verts}</vertices><triangles>{tris}</triangles>"
        "</mesh></object>"
    )
    objects = "".join(obj.format(oid=i + 1) for i in range(n_objects))
    tf = f' transform="{transform}"' if transform else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<model unit="millimeter" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
        f"<resources>{objects}</resources>"
        f'<build><item objectid="1"{tf}/></build></model>'
    )


def _write_3mf(path: Path, model_xml: str) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("_rels/.rels", _RELS)
        zf.writestr("3D/3dmodel.model", model_xml)


def test_3mf_cube_reads_watertight(tmp_path: Path) -> None:
    path = tmp_path / "cube.3mf"
    _write_3mf(path, _model_xml())
    surf = read_3mf(path)
    assert surf.n_vertices == 8
    assert surf.n_faces == 12
    assert compute_quality(surf).watertight


def test_3mf_multiple_meshes_out_of_scope(tmp_path: Path) -> None:
    path = tmp_path / "two.3mf"
    _write_3mf(path, _model_xml(n_objects=2))
    with pytest.raises(GeometryError, match="exactly one mesh"):
        read_3mf(path)


def test_3mf_transform_out_of_scope(tmp_path: Path) -> None:
    path = tmp_path / "tf.3mf"
    _write_3mf(path, _model_xml(transform="1 0 0 0 1 0 0 0 1 10 0 0"))
    with pytest.raises(GeometryError, match="transform"):
        read_3mf(path)


def test_3mf_not_a_zip_fails_loud(tmp_path: Path) -> None:
    path = tmp_path / "junk.3mf"
    path.write_bytes(b"definitely not a zip archive")
    with pytest.raises(GeometryError, match="not a ZIP"):
        read_3mf(path)

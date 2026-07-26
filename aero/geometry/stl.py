"""STL reading/writing — pure numpy, no dependencies (Stage 18, ADR-033).

Reads both binary and ASCII STL. STL is a *triangle soup* (each facet repeats its
corner coordinates, nothing is shared), so the reader welds **bitwise-identical**
coordinates into shared vertices — that is a lossless representation change, not a
repair, and it is what makes edge-based topology checks (watertightness, manifoldness)
meaningful. Tolerance-based merging of *nearly*-equal vertices is a declared repair
action (:mod:`aero.geometry.repair`), never something the reader does silently.

Format detection does not trust the ``solid`` prefix (real-world binary STL files
start with ``solid`` all the time): a file is binary iff its size matches the binary
layout (80-byte header + uint32 count + 50 bytes/facet). Malformed files raise
:class:`~aero.geometry._base.GeometryError`.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

import numpy as np

from aero.geometry._base import GeometryError, TriSurface, weld_corners

__all__ = ["read_stl", "write_stl"]

_BINARY_HEADER_BYTES = 80
_BINARY_FACET_BYTES = 50  # 12 float32 (normal + 3 corners) + uint16 attribute
_ASCII_VERTEX_RE = re.compile(rb"vertex\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)", re.IGNORECASE)
_ASCII_FACET_RE = re.compile(rb"facet\s+normal", re.IGNORECASE)


_weld = weld_corners  # exact-weld normalization shared with the STEP loader


def _read_binary(data: bytes, path: Path) -> TriSurface:
    (n_facets,) = struct.unpack_from("<I", data, _BINARY_HEADER_BYTES)
    expected = _BINARY_HEADER_BYTES + 4 + n_facets * _BINARY_FACET_BYTES
    if len(data) != expected:
        raise GeometryError(
            f"{path}: binary STL declares {n_facets} facets "
            f"({expected} bytes) but the file is {len(data)} bytes"
        )
    if n_facets == 0:
        raise GeometryError(f"{path}: binary STL declares 0 facets")
    records = np.frombuffer(
        data,
        dtype=np.dtype([("normal", "<f4", (3,)), ("corners", "<f4", (3, 3)), ("attr", "<u2")]),
        count=n_facets,
        offset=_BINARY_HEADER_BYTES + 4,
    )
    corners = records["corners"].astype(np.float64)
    if not np.isfinite(corners).all():
        raise GeometryError(f"{path}: binary STL contains non-finite vertex coordinates")
    return _weld(corners)


def _read_ascii(data: bytes, path: Path) -> TriSurface:
    n_facets = len(_ASCII_FACET_RE.findall(data))
    raw = _ASCII_VERTEX_RE.findall(data)
    if n_facets == 0 or not raw:
        raise GeometryError(f"{path}: not a parseable STL (no facets found)")
    if len(raw) != 3 * n_facets:
        raise GeometryError(
            f"{path}: ASCII STL is malformed — {n_facets} facets but "
            f"{len(raw)} vertex lines (expected {3 * n_facets})"
        )
    try:
        flat = np.array(raw, dtype=np.float64)
    except ValueError as exc:
        raise GeometryError(f"{path}: ASCII STL has unparseable vertex coordinates") from exc
    if not np.isfinite(flat).all():
        raise GeometryError(f"{path}: ASCII STL contains non-finite vertex coordinates")
    return _weld(flat.reshape(-1, 3, 3))


def read_stl(path: Path) -> TriSurface:
    """Read an STL file (binary or ASCII) into an indexed :class:`TriSurface`."""
    data = path.read_bytes()
    if len(data) < _BINARY_HEADER_BYTES + 4:
        raise GeometryError(f"{path}: too small to be an STL file ({len(data)} bytes)")
    (n_facets,) = struct.unpack_from("<I", data, _BINARY_HEADER_BYTES)
    if len(data) == _BINARY_HEADER_BYTES + 4 + n_facets * _BINARY_FACET_BYTES and n_facets > 0:
        return _read_binary(data, path)
    return _read_ascii(data, path)


def write_stl(surface: TriSurface, path: Path, *, binary: bool = True) -> None:
    """Write a :class:`TriSurface` as STL (binary by default)."""
    tri = surface.triangle_corners()
    cross = surface.face_cross()
    norms = np.linalg.norm(cross, axis=1, keepdims=True)
    normals = np.divide(cross, norms, out=np.zeros_like(cross), where=norms > 0.0)
    if binary:
        records = np.zeros(
            surface.n_faces,
            dtype=np.dtype([("normal", "<f4", (3,)), ("corners", "<f4", (3, 3)), ("attr", "<u2")]),
        )
        records["normal"] = normals.astype(np.float32)
        records["corners"] = tri.astype(np.float32)
        header = b"aero-research-platform binary STL".ljust(_BINARY_HEADER_BYTES, b"\0")
        path.write_bytes(header + struct.pack("<I", surface.n_faces) + records.tobytes())
        return
    lines = ["solid aero"]
    for n, corners in zip(normals, tri, strict=True):
        lines.append(f"  facet normal {n[0]:.9e} {n[1]:.9e} {n[2]:.9e}")
        lines.append("    outer loop")
        for c in corners:
            lines.append(f"      vertex {c[0]:.9e} {c[1]:.9e} {c[2]:.9e}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append("endsolid aero")
    path.write_text("\n".join(lines) + "\n")

"""Minimal 3MF reading — stdlib ``zipfile`` + ``xml.etree`` + numpy (Stage 18, ADR-033).

Deliberately bounded scope (declared, fail-loud): a 3MF package whose build references
exactly **one** mesh object with **no transform and no components** is read; anything
richer (assemblies, per-item transforms, beam lattices) raises
:class:`~aero.geometry._base.GeometryError` naming what was found — never a silent
partial read. Coordinates are taken verbatim (3MF's default unit is millimetre; unit
handling belongs to the case setup, and the recorded quality report carries the bbox so
a unit mistake is visible immediately).

XML parsing note: 3MF model files are trusted local inputs here (DVC-tracked reference
geometry), parsed with the stdlib parser; we do not fetch remote entities.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

from aero.geometry._base import GeometryError, TriSurface

__all__ = ["read_3mf"]

_CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
_RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_MODEL_REL_TYPE = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"


def _model_path(zf: zipfile.ZipFile, path: Path) -> str:
    """Resolve the 3D-model part path from the package relationships."""
    try:
        rels = zf.read("_rels/.rels")
    except KeyError as exc:
        raise GeometryError(f"{path}: 3MF package has no _rels/.rels") from exc
    root = ElementTree.fromstring(rels)
    for rel in root.iter(f"{{{_RELS_NS}}}Relationship"):
        if rel.get("Type") == _MODEL_REL_TYPE:
            target = rel.get("Target", "")
            return target.lstrip("/")
    raise GeometryError(f"{path}: 3MF package declares no 3D-model relationship")


def read_3mf(path: Path) -> TriSurface:
    """Read a single-mesh 3MF package into an indexed :class:`TriSurface`."""
    try:
        with zipfile.ZipFile(path) as zf:
            model_xml = zf.read(_model_path(zf, path))
    except zipfile.BadZipFile as exc:
        raise GeometryError(f"{path}: not a 3MF package (not a ZIP archive)") from exc
    except KeyError as exc:
        raise GeometryError(f"{path}: 3MF model part missing from package") from exc

    try:
        root = ElementTree.fromstring(model_xml)
    except ElementTree.ParseError as exc:
        raise GeometryError(f"{path}: 3MF model XML is malformed") from exc

    ns = {"m": _CORE_NS}
    if root.findall(".//m:component", ns):
        raise GeometryError(
            f"{path}: 3MF uses assembly components — out of the declared single-mesh scope"
        )
    items = root.findall(".//m:build/m:item", ns)
    for item in items:
        if item.get("transform") is not None:
            raise GeometryError(
                f"{path}: 3MF build item carries a transform — out of the declared scope"
            )
    meshes = root.findall(".//m:object/m:mesh", ns)
    if len(meshes) != 1:
        raise GeometryError(
            f"{path}: expected exactly one mesh object in the 3MF model, found {len(meshes)}"
        )
    mesh = meshes[0]

    try:
        vertices = np.array(
            [
                (float(v.get("x", "")), float(v.get("y", "")), float(v.get("z", "")))
                for v in mesh.findall("./m:vertices/m:vertex", ns)
            ],
            dtype=np.float64,
        )
        faces = np.array(
            [
                (int(t.get("v1", "")), int(t.get("v2", "")), int(t.get("v3", "")))
                for t in mesh.findall("./m:triangles/m:triangle", ns)
            ],
            dtype=np.int64,
        )
    except ValueError as exc:
        raise GeometryError(f"{path}: 3MF mesh has unparseable vertex/triangle data") from exc
    if vertices.size == 0 or faces.size == 0:
        raise GeometryError(f"{path}: 3MF mesh is empty")
    return TriSurface(vertices, faces)

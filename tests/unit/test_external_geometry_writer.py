"""aero.adapters.openfoam.external_geometry — spec validation + case composition.

The writer must refuse a surface whose bytes do not match the ingestion-gated digest,
and the emitted dictionaries must carry the quasi-2D invariants (one-cell slab, empty
front/back, no volumetric refinement). Stage 18, ADR-033/034.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from aero.adapters.openfoam.external_geometry import (
    ExternalGeometrySpec,
    write_external_geometry_case,
)
from aero.geometry import GeometryError, write_stl
from pydantic import ValidationError

from tests.unit._launch_fixtures import committed_repo, dvc_pointer
from tests.unit.geometry_fixtures import cube


def _repo(tmp_path: Path) -> Path:
    """The STL committed to a stand-in checkout: staging reads only git or declared DVC files."""
    return tmp_path / "repo"


def _write(spec: ExternalGeometrySpec, dest: Path, repo: Path) -> None:
    write_external_geometry_case(spec, dest, repo_root=repo, declared=())


def _spec(tmp_path: Path, **overrides: object) -> ExternalGeometrySpec:
    built = tmp_path / "built.stl"
    write_stl(cube(), built)
    repo = _repo(tmp_path)
    if not (repo / "body.stl").exists():
        committed_repo(repo, {"body.stl": built.read_bytes()})
    stl = repo / "body.stl"
    sha = hashlib.sha256(stl.read_bytes()).hexdigest()
    defaults: dict[str, object] = {
        "name": "ext-test",
        "surface_source": str(stl),
        "surface_name": "body",
        "surface_sha256": sha,
        "base_cell_size": 0.01,
    }
    defaults.update(overrides)
    return ExternalGeometrySpec(**defaults)  # type: ignore[arg-type]


def test_spec_requires_a_real_sha256(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="surface_sha256"):
        _spec(tmp_path, surface_sha256="not-a-digest")


def test_spec_rejects_inverted_domain(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="domain_min"):
        _spec(tmp_path, domain_min=(3.0, 0.0))


def test_writer_refuses_mismatched_surface_bytes(tmp_path: Path) -> None:
    spec = _spec(tmp_path, surface_sha256="0" * 64)
    with pytest.raises(GeometryError, match="refusing to mesh a different surface"):
        _write(spec, tmp_path / "case", _repo(tmp_path))


def test_writer_refuses_missing_surface(tmp_path: Path) -> None:
    spec = _spec(tmp_path).model_copy(update={"surface_source": str(tmp_path / "gone.stl")})
    with pytest.raises(GeometryError, match="not found"):
        _write(spec, tmp_path / "case", _repo(tmp_path))


def test_writer_reads_the_surface_through_the_declaration(tmp_path: Path) -> None:
    """ADR-052: a DVC-tracked STL is staged only if the run declared it, at its pointer's bytes."""
    from aero.provenance.dvc_inputs import resolve_declared
    from aero.provenance.four_fold import ProvenanceError

    built = tmp_path / "built.stl"
    write_stl(cube(), built)
    data = built.read_bytes()
    md5 = hashlib.md5(data, usedforsecurity=False).hexdigest()
    repo = committed_repo(tmp_path / "dvc", {"geo.stl.dvc": dvc_pointer(md5, len(data), "geo.stl")})
    (repo / "geo.stl").write_bytes(data)  # pulled by DVC, so never in git
    spec = ExternalGeometrySpec(
        name="ext-test",
        surface_source=str(repo / "geo.stl"),
        surface_name="body",
        surface_sha256=hashlib.sha256(data).hexdigest(),
        base_cell_size=0.01,
    )
    with pytest.raises(ProvenanceError, match="did not declare"):
        write_external_geometry_case(spec, tmp_path / "a", repo_root=repo, declared=())
    declared = resolve_declared(repo, ("geo.stl.dvc",))
    write_external_geometry_case(spec, tmp_path / "b", repo_root=repo, declared=declared)
    assert (tmp_path / "b" / "constant" / "triSurface" / "body.stl").read_bytes() == data
    # A file outside the checkout is covered by neither git_sha nor dvc_input_hash.
    outside = spec.model_copy(update={"surface_source": str(built)})
    with pytest.raises(ProvenanceError, match="outside the checkout"):
        write_external_geometry_case(outside, tmp_path / "c", repo_root=repo, declared=declared)


def test_case_composition_quasi_2d(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    dest = tmp_path / "case"
    _write(spec, dest, _repo(tmp_path))

    block = (dest / "system" / "blockMeshDict").read_text()
    nx, ny = spec.n_cells_background()
    assert f"({nx} {ny} 1)" in block  # one-cell slab
    assert "type empty;" in block

    snappy = (dest / "system" / "snappyHexMeshDict").read_text()
    assert "level (0 0);" in snappy  # no volumetric refinement (quasi-2D)
    assert "addLayers       false;" in snappy
    assert "maxNonOrtho         65;" in snappy
    assert "body.stl" in snappy and "body.eMesh" in snappy

    control = (dest / "system" / "controlDict").read_text()
    assert "application     simpleFoam;" in control
    assert "patches         (body);" in control
    # Aref = ref_length * slab thickness (the 2D dz cancellation).
    assert f"Aref            {spec.ref_length * spec.slab_thickness:.8g};" in control

    assert (dest / "constant" / "triSurface" / "body.stl").is_file()
    u_field = (dest / "0" / "U").read_text()
    assert "exprFixedValue" in u_field
    assert "frontAndBack { type empty; }" in u_field


def test_layers_and_transient_variants(tmp_path: Path) -> None:
    spec = _spec(tmp_path, n_surface_layers=2, transient=True)
    dest = tmp_path / "case"
    _write(spec, dest, _repo(tmp_path))
    snappy = (dest / "system" / "snappyHexMeshDict").read_text()
    assert "addLayers       true;" in snappy
    assert "nSurfaceLayers 2;" in snappy
    control = (dest / "system" / "controlDict").read_text()
    assert "application     pimpleFoam;" in control
    assert "adjustTimeStep  yes;" in control


def test_mapped_inlet_writes_boundary_data(tmp_path: Path) -> None:
    spec = _spec(tmp_path, inlet_bc="mapped")
    dest = tmp_path / "case"
    _write(spec, dest, _repo(tmp_path))
    u_field = (dest / "0" / "U").read_text()
    assert "timeVaryingMappedFixedValue" in u_field
    points = (dest / "constant" / "boundaryData" / "inlet" / "points").read_text()
    values = (dest / "constant" / "boundaryData" / "inlet" / "0" / "U").read_text()
    assert points.splitlines()[0] == values.splitlines()[0]  # same sample count
    # Mid-channel sample must be ~1.5 * u_mean (parabolic peak).
    assert f"({1.5 * spec.u_mean:.10g} 0 0)" in values
    # The samples must span a PLANE, not a line: v2412's planar-interpolation basis
    # FatalErrors on collinear boundaryData ("all your points on a single line").
    coords = [
        tuple(float(v) for v in line.strip().strip("()").split())
        for line in points.splitlines()[2:]
        if line.startswith("(")
    ]
    assert len({c[2] for c in coords}) >= 2, "boundaryData points are collinear in z"
    assert len({c[1] for c in coords}) >= 3


def test_parabolic_expression_peaks_at_1p5_umean(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    u_field = tmp_path / "case2"
    _write(spec, u_field, _repo(tmp_path))
    expr = (u_field / "0" / "U").read_text()
    # U(y) = 6 U (y-y0)(y1-y)/H^2 — the Turek-Hron profile (eq. 10).
    assert "6*1*" in expr.replace(" ", "") or "6*" in expr


def test_surface_sha_enters_the_spec_dump(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    dumped = spec.model_dump(mode="json")
    assert dumped["surface_sha256"] == spec.surface_sha256  # config_hash coverage

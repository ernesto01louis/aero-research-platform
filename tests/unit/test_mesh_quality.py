"""aero.adapters.openfoam.mesh_quality — checkMesh parsing + the M-gate.

Canned checkMesh outputs (v2412 layout): a clean pass, threshold breaches, negative
volumes, and garbled output — the last must FAIL the gate (missing metrics never read
as a pass). Stage 18, ADR-034.
"""

from __future__ import annotations

from aero.adapters.openfoam.mesh_quality import MeshQualityGate, parse_checkmesh

_CLEAN = """
Mesh stats
    points:           84616
    faces:            166376
    internal faces:   81964
    cells:            41208
    faces per cell:   6.03
    boundary patches: 5

Checking geometry...
    Overall domain bounding box (0 0 0) (2.5 0.41 0.005)
    Mesh has 2 geometric (non-empty/wedge) directions (1 1 0)
    Max aspect ratio = 3.4218 OK.
    Minimum face area = 2.1e-06. Maximum face area = 2.6e-05.  Face area magnitudes OK.
    Min volume = 1.2043e-08. Max volume = 1.3e-07.  Total volume = 0.00504.  Cell volumes OK.
    Mesh non-orthogonality Max: 52.31 average: 8.144
    Non-orthogonality check OK.
    Face pyramids OK.
    Max skewness = 1.9032 OK.
    Coupled point location match (average 0) OK.

Mesh OK.

End
"""

_FAILING = """
Mesh stats
    cells:            38891

Checking geometry...
    Max aspect ratio = 41.2 OK.
    Min volume = 4.4e-11. Max volume = 1.1e-07.  Total volume = 0.005.  Cell volumes OK.
    Mesh non-orthogonality Max: 78.02 average: 11.4
   *Number of severely non-orthogonal (> 70 degrees) faces: 44.
    Non-orthogonality check OK.
 ***Max skewness = 8.71, 12 highly skew faces detected which may impair the quality of the results
    Coupled point location match (average 0) OK.

Failed 1 mesh checks.

End
"""

_NEGATIVE = """
Mesh stats
    cells:            12000

Checking geometry...
    Max aspect ratio = 5.0 OK.
 ***Zero or negative cell volume detected.  Minimum negative volume: -2.1e-12, Number of negative volume cells: 5
    Mesh non-orthogonality Max: 44.0 average: 9.0
    Max skewness = 2.2 OK.

Failed 2 mesh checks.

End
"""


def test_clean_output_parses_and_passes() -> None:
    metrics = parse_checkmesh(_CLEAN)
    assert metrics.mesh_ok
    assert metrics.n_cells == 41208
    assert metrics.max_non_orthogonality == 52.31
    assert metrics.max_skewness == 1.9032
    assert not metrics.negative_volumes
    result = MeshQualityGate().evaluate(metrics)
    assert result.passed
    assert result.failures == ()


def test_threshold_breaches_fail_by_name() -> None:
    result = MeshQualityGate().evaluate(parse_checkmesh(_FAILING))
    assert not result.passed
    text = " | ".join(result.failures)
    assert "M1" in text  # no "Mesh OK"
    assert "M2" in text  # non-ortho 78.02 > 65
    assert "M3" in text  # skew 8.71 > 4


def test_negative_volumes_fail_m4() -> None:
    result = MeshQualityGate().evaluate(parse_checkmesh(_NEGATIVE))
    assert not result.passed
    assert any(f.startswith("M4") for f in result.failures)


def test_min_cells_floor_fails_m5() -> None:
    gate = MeshQualityGate(min_cells=50000)
    result = gate.evaluate(parse_checkmesh(_CLEAN))
    assert not result.passed
    assert any(f.startswith("M5") for f in result.failures)


def test_garbled_output_never_reads_as_a_pass() -> None:
    metrics = parse_checkmesh("Segmentation fault (core dumped)")
    assert not metrics.mesh_ok
    assert metrics.n_cells is None
    result = MeshQualityGate().evaluate(metrics)
    assert not result.passed
    # Every gated-but-missing metric is named, loudly.
    text = " | ".join(result.failures)
    assert "M2" in text and "M3" in text and "M5" in text


def test_gate_thresholds_are_the_preregistered_defaults() -> None:
    gate = MeshQualityGate()
    assert gate.max_non_orthogonality == 65.0
    assert gate.max_skewness == 4.0
    assert gate.require_mesh_ok
    assert gate.forbid_negative_volumes
    assert gate.min_cells == 1000

"""Stage 10 — forward-regime laminar NACA 0012 (host-side).

Pins the laminar airfoil wiring: the C-grid writer emits a `simulationType
laminar` case with only U and p (no k/omega/nut), the symmetry + low-Re-Cd
metrics, and the reference. The cluster Cd/Cl check is the slow test in
tests/vv/test_forward_regime_laminar_airfoil.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.openfoam.case_writer import write_case
from aero.vv.forward_regime import FORWARD_REGIME_CASES, LaminarAirfoil

pytestmark = pytest.mark.stage_10

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_case_is_registered_and_laminar() -> None:
    assert "laminar_airfoil_naca0012" in FORWARD_REGIME_CASES
    spec = LaminarAirfoil().case_spec()
    assert spec.turbulence_model == "laminar"
    assert spec.reynolds == 1.0e3
    assert spec.aoa_deg == 0.0
    assert spec.trailing_edge_thickness == 0.0  # sharp TE (blunt is the rejected remedy)


def test_case_generates_a_laminar_cgrid_case(tmp_path: Path) -> None:
    write_case(LaminarAirfoil().case_spec(), tmp_path)
    zero_fields = sorted(p.name for p in (tmp_path / "0").iterdir())
    assert zero_fields == ["U", "p"]
    tp = (tmp_path / "constant" / "turbulenceProperties").read_text()
    assert "simulationType  laminar;" in tp
    assert "RASModel" not in tp


def test_metrics_are_symmetry_and_low_re_drag() -> None:
    metrics = {m.name: m for m in LaminarAirfoil().metrics()}
    assert metrics["cl"].comparison == "absolute"  # Cl=0 by symmetry
    assert metrics["cl"].tolerance == pytest.approx(0.01)
    assert metrics["cd"].comparison == "relative"
    assert metrics["cd"].tolerance == pytest.approx(0.10)


def test_reference_values() -> None:
    ref = LaminarAirfoil().reference(_REPO_ROOT)
    assert ref.scalars["cd"] == pytest.approx(0.12)
    assert ref.scalars["cl"] == 0.0

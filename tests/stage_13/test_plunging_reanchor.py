"""Stage 13 host tests — the plunging re-anchor + kOmegaSSTLM transition path.

Pure/no-cluster: the St-parametrized variants register with distinct names + specs, the
kOmegaSSTLM moving case renders the transition fields with moving-wall BCs (laminar
unchanged), and the refined_dt seam scales the timestep for a space+time GCI.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.openfoam.plunging_airfoil import write_plunging_airfoil_case
from aero.vv.unsteady import UNSTEADY_CASES
from aero.vv.unsteady.plunging_airfoil import PlungingAirfoilHG2007

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _st(spec: object) -> float:
    m = spec.motion  # type: ignore[attr-defined]
    return 2.0 * m.frequency * m.amplitude


# --- registry variants --------------------------------------------------------
def test_reanchor_variants_registered() -> None:
    for key in (
        "plunging_airfoil_hg2007",  # base St=0.4 laminar (unchanged name)
        "plunging_airfoil_hg2007_st02",
        "plunging_airfoil_hg2007_st02_lm",
        "plunging_airfoil_hg2007_st03",
        "plunging_airfoil_hg2007_st03_lm",
    ):
        assert key in UNSTEADY_CASES, f"missing variant {key}"


def test_reanchor_strouhal_and_model() -> None:
    st02 = UNSTEADY_CASES["plunging_airfoil_hg2007_st02"].case_spec()
    assert _st(st02) == pytest.approx(0.2, abs=1e-6)
    assert st02.turbulence_model == "laminar"
    st02lm = UNSTEADY_CASES["plunging_airfoil_hg2007_st02_lm"].case_spec()
    assert _st(st02lm) == pytest.approx(0.2, abs=1e-6)
    assert st02lm.turbulence_model == "kOmegaSSTLM"


def test_reanchor_reference_uses_variant_strouhal() -> None:
    # St=0.2 -> C_T ref 0.20; St=0.3 -> 0.22 (the corrected in-range HG points).
    ref02 = UNSTEADY_CASES["plunging_airfoil_hg2007_st02"].reference(_REPO_ROOT)
    assert ref02.scalars["thrust_coefficient"] == pytest.approx(0.20)
    ref03 = UNSTEADY_CASES["plunging_airfoil_hg2007_st03"].reference(_REPO_ROOT)
    assert ref03.scalars["thrust_coefficient"] == pytest.approx(0.22)


# --- transition moving case ---------------------------------------------------
def test_transition_moving_case_writes_transition_fields(tmp_path: Path) -> None:
    spec = UNSTEADY_CASES["plunging_airfoil_hg2007_st02_lm"].case_spec()
    write_plunging_airfoil_case(spec, tmp_path)
    fields = {p.name for p in (tmp_path / "0").iterdir()}
    assert {"gammaInt", "ReThetat", "k", "omega", "nut"} <= fields  # full transition set
    # The moving wall keeps movingWallVelocity on U even with the turbulence model.
    assert "movingWallVelocity" in (tmp_path / "0" / "U").read_text()
    assert "internalField   uniform 1;" in (tmp_path / "0" / "gammaInt").read_text()
    schemes = (tmp_path / "system" / "fvSchemes").read_text()
    assert "div(phi,gammaInt)" in schemes and "div(phi,ReThetat)" in schemes
    assert (
        "RASModel        kOmegaSSTLM;"
        in (tmp_path / "constant" / "turbulenceProperties").read_text()
    )


def test_laminar_moving_case_unaffected(tmp_path: Path) -> None:
    spec = UNSTEADY_CASES["plunging_airfoil_hg2007_st02"].case_spec()
    write_plunging_airfoil_case(spec, tmp_path)
    fields = {p.name for p in (tmp_path / "0").iterdir()}
    assert fields == {"U", "p", "pointDisplacement"}  # laminar: no turbulence transport


# --- refined_dt seam ----------------------------------------------------------
def test_refined_dt_scales_max_courant() -> None:
    base = PlungingAirfoilHG2007(strouhal=0.2)
    coarse = base.refined_dt(2.0)
    assert coarse.case_spec().max_courant == pytest.approx(2.0 * base.case_spec().max_courant)
    with pytest.raises(ValueError, match="refined_dt"):
        base.refined_dt(0.0)


def test_refined_preserves_variant_identity() -> None:
    # A spatially-refined transition variant keeps its model + name suffix.
    base = PlungingAirfoilHG2007(strouhal=0.2, turbulence_model="kOmegaSSTLM")
    coarse = base.refined(1.7)
    assert coarse.case_spec().turbulence_model == "kOmegaSSTLM"
    assert coarse.name == "plunging_airfoil_hg2007_st02_lm"

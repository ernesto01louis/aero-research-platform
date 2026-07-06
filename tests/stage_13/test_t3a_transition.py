"""Stage 13 host tests — the ported ERCOFTAC T3A transitional-flat-plate case.

Pure/no-cluster: the case writer renders a valid tree, and the `T3AFlatPlate`
BenchmarkCase conforms to the protocol (case_spec/reference/metrics/evaluate/refined) with
the transition-onset reference derived from the committed Cf data. The Cf(x) solve itself
runs on the cluster (Stage-13 B1).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.openfoam.t3a import T3ASpec, write_t3a_case
from aero.vv._base import BenchmarkCase
from aero.vv.ercoftac import ERCOFTAC_CASES
from aero.vv.ercoftac.t3a_flat_plate import T3AFlatPlate

_REPO_ROOT = Path(__file__).resolve().parents[2]


# --- case writer --------------------------------------------------------------
def test_write_t3a_case_produces_full_tree(tmp_path: Path) -> None:
    write_t3a_case(T3ASpec(name="t3a"), tmp_path)
    for rel in (
        "system/blockMeshDict",
        "system/controlDict",
        "system/fvSchemes",
        "system/fvSolution",
        "constant/transportProperties",
        "constant/turbulenceProperties",
        "0/U",
        "0/p",
        "0/k",
        "0/omega",
        "0/nut",
        "0/gammaInt",
        "0/ReThetat",
    ):
        assert (tmp_path / rel).is_file(), f"missing {rel}"


def test_t3a_mesh_and_turbulence(tmp_path: Path) -> None:
    write_t3a_case(T3ASpec(name="t3a"), tmp_path)
    bm = (tmp_path / "system" / "blockMeshDict").read_text()
    assert bm.count("hex (") == 11  # ported 11-block mesh
    assert "name    frontAndBack;" in bm  # explicit 2-D span patch
    assert "type wall;" in bm  # the plate patch
    tp = (tmp_path / "constant" / "turbulenceProperties").read_text()
    assert "RASModel        kOmegaSSTLM;" in tp


def test_t3a_transition_fields_and_sampler(tmp_path: Path) -> None:
    write_t3a_case(T3ASpec(name="t3a"), tmp_path)
    gamma = (tmp_path / "0" / "gammaInt").read_text()
    assert "internalField   uniform 1;" in gamma
    rethetat = (tmp_path / "0" / "ReThetat").read_text()
    assert "internalField   uniform 160.99;" in rethetat  # tutorial free-stream Re_theta
    u = (tmp_path / "0" / "U").read_text()
    assert "uniform (5.4 0 0)" in u  # dimensional free-stream
    # The controlDict must write the platform's plate sampler (not the tutorial graphs).
    cd = (tmp_path / "system" / "controlDict").read_text()
    assert "wallShearStress1" in cd and "sampleWall" in cd
    assert "patches     (plate);" in cd


def test_t3a_mesh_factor_scales_cell_counts(tmp_path: Path) -> None:
    write_t3a_case(T3ASpec(name="t3a", mesh_factor=0.5), tmp_path / "coarse")
    write_t3a_case(T3ASpec(name="t3a", mesh_factor=1.0), tmp_path / "base")
    coarse = (tmp_path / "coarse" / "system" / "blockMeshDict").read_text()
    base = (tmp_path / "base" / "system" / "blockMeshDict").read_text()
    # The first block is (7 20 1) at factor 1 -> (4 10 1) at factor 0.5 (7*0.5 rounds to 4).
    assert "(4 10 1)" in coarse
    assert "(7 20 1)" in base


# --- BenchmarkCase conformance ------------------------------------------------
def test_t3a_case_conforms_to_protocol() -> None:
    case = T3AFlatPlate()
    assert isinstance(case, BenchmarkCase)
    assert case.name == "t3a_flat_plate_transition"
    assert ERCOFTAC_CASES[case.name] is not None


def test_t3a_reference_loads_cf_and_onset() -> None:
    case = T3AFlatPlate()
    ref = case.reference(_REPO_ROOT)
    assert "cf" in ref.series
    assert len(ref.series["cf"].x) == 16
    # The onset Re_x is derived at the Cf minimum (x = 0.395 m): 5.4*0.395/1.5e-5 ~= 1.42e5.
    onset = ref.scalars["transition_onset_rex"]
    assert 1.3e5 < onset < 1.55e5


def test_t3a_metrics_are_onset_and_cf() -> None:
    metrics = {m.name: m for m in T3AFlatPlate().metrics()}
    assert metrics["transition_onset_rex"].kind == "scalar"
    assert metrics["transition_onset_rex"].tolerance == pytest.approx(0.20)
    assert metrics["cf"].kind == "pointwise"
    assert metrics["cf"].comparison == "normalized"


def test_t3a_refined_coarsens_mesh() -> None:
    base = T3AFlatPlate()
    coarse = base.refined(2.0)
    assert coarse.case_spec().mesh_factor == pytest.approx(0.5)
    assert base.case_spec().mesh_factor == pytest.approx(1.0)

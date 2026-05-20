"""Stage 05 unit tests for the TMR benchmark cases — pure, no cluster."""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.vv._base import BenchmarkCase
from aero.vv.tmr import TMR_CASES

pytestmark = pytest.mark.stage_05

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_registry_has_the_three_tmr_cases() -> None:
    assert set(TMR_CASES) == {"flat_plate_te", "bump_2d", "naca0012_verification"}


@pytest.mark.parametrize("case", TMR_CASES.values(), ids=list(TMR_CASES))
def test_case_satisfies_protocol(case: BenchmarkCase) -> None:
    assert isinstance(case, BenchmarkCase)
    assert case.name and case.description
    assert case.case_spec() is not None
    assert len(case.metrics()) >= 1


@pytest.mark.parametrize("case", TMR_CASES.values(), ids=list(TMR_CASES))
def test_refined_coarsens_the_mesh(case: BenchmarkCase) -> None:
    base = case.case_spec()
    coarse = case.refined(1.7).case_spec()
    # `refined(ratio>1)` must reduce the cell counts (a coarser GCI grid).
    base_cells = sum(v for k, v in base.model_dump().items() if k.startswith("n_"))
    coarse_cells = sum(v for k, v in coarse.model_dump().items() if k.startswith("n_"))
    assert coarse_cells < base_cells
    assert case.refined(1.0).case_spec() == base  # ratio 1.0 is the base grid


def test_flat_plate_reference_loads_from_intree_data() -> None:
    ref = TMR_CASES["flat_plate_te"].reference(_REPO_ROOT)
    assert "cf" in ref.series
    assert len(ref.series["cf"].x) >= 10


def test_naca0012_reference_is_a_scalar_cd() -> None:
    ref = TMR_CASES["naca0012_verification"].reference(_REPO_ROOT)
    assert ref.scalars["cd"] == pytest.approx(0.00812, abs=1e-4)


def test_bump_reference_loads_cp_and_cf() -> None:
    ref = TMR_CASES["bump_2d"].reference(_REPO_ROOT)
    assert {"cp", "cf"} <= set(ref.series)
    assert len(ref.series["cp"].x) >= 100

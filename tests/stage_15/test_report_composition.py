"""Stage 15 — the matched-condition delta-UQ + OptimizationResult composition (no CFD).

Pins the GO/NO-GO contract: a delta that clears k*U95 composes a thesis-grade ReportableResult
carrying a CFD-verified OptimizationResult; a delta within k*U95 is the honest NO-GO (plain
quantities, validated tier — never a manufactured claim, Invariant 10). Also the delta-GCI math
and the selection-bias / dirty-SHA guards.
"""

from __future__ import annotations

import pytest
from aero.optimize.report import MatchedGridDelta, compose_result, gci_2grid_fraction
from aero.provenance.four_fold import ProvenanceTuple
from pydantic import ValidationError

pytestmark = pytest.mark.stage_15


def _prov(*, dirty: bool = False) -> ProvenanceTuple:
    return ProvenanceTuple(
        git_sha="a" * 40 + ("-dirty" if dirty else ""),
        dvc_input_hash="0" * 64,
        container_sif_sha256="1" * 64,
        config_hash="2" * 64,
    )


def _delta(opt_fine: float) -> MatchedGridDelta:
    # baseline ~2.0, optimum = opt_fine; small matched-grid discretization spread.
    return MatchedGridDelta(
        quantity="lift_to_drag",
        baseline_fine=2.0,
        baseline_coarse=2.05,
        optimum_fine=opt_fine,
        optimum_coarse=opt_fine * 1.03,
        refinement_ratio=1.7,
    )


def test_gci_2grid_fraction() -> None:
    # |coarse-fine|/|fine| = 0.1/1.0; Fs=3; (1.7^2-1)=1.89 -> 3*0.1/1.89
    assert gci_2grid_fraction(1.0, 1.1, ratio=1.7) == pytest.approx(3.0 * 0.1 / (1.7**2 - 1.0))


def test_delta_gci_cancels_matched_error() -> None:
    d = _delta(3.0)
    # the delta (1.0) is large vs its GCI-on-the-delta U95
    assert d.delta_fine == pytest.approx(1.0)
    assert d.u95_delta_numerical < 0.2
    assert d.is_significant(higher_is_better=True, k=2.0)


def test_go_composes_thesis_grade() -> None:
    result, is_go = compose_result(
        case_name="airfoil_opt",
        objective="maximize lift_to_drag",
        quantity="lift_to_drag",
        higher_is_better=True,
        design_variables={"max_camber": 0.04, "camber_position": 0.4},
        delta=_delta(3.0),
        cfd_verified=_prov(),
        n_candidates=15,
    )
    assert is_go is True
    assert result.validation_tag == "thesis-grade"
    assert result.optimization is not None
    claim = result.optimization.improvement
    assert claim.delta > claim.required_margin  # cleared k*U95
    assert result.optimization.held_out_verification is True
    assert result.optimization.n_candidates == 15


def test_nogo_reports_plain_quantities() -> None:
    result, is_go = compose_result(
        case_name="airfoil_opt",
        objective="maximize lift_to_drag",
        quantity="lift_to_drag",
        higher_is_better=True,
        design_variables={"max_camber": 0.001},
        delta=_delta(2.01),  # delta ~0.01, within U95
        cfd_verified=_prov(),
        n_candidates=15,
    )
    assert is_go is False
    assert result.validation_tag == "validated"
    assert result.optimization is None
    assert {q.name for q in result.quantities} == {
        "lift_to_drag_baseline",
        "lift_to_drag_optimum",
    }


def test_go_with_dirty_sha_rejected() -> None:
    # A thesis-grade optimization result cannot carry a -dirty SHA (P1b).
    with pytest.raises(ValidationError, match="dirty"):
        compose_result(
            case_name="airfoil_opt",
            objective="o",
            quantity="lift_to_drag",
            higher_is_better=True,
            design_variables={},
            delta=_delta(3.0),
            cfd_verified=_prov(dirty=True),
            n_candidates=15,
        )


def test_best_of_n_requires_held_out() -> None:
    # OptimizationResult enforces held_out_verification when n_candidates>1; compose_result always
    # sets it True, so a hand-built result without it must raise (guard is live).
    from aero.vv.reportable import ComposedDeltaU95, ImprovementClaim, OptimizationResult

    claim = ImprovementClaim(
        quantity="lift_to_drag",
        kind="steady",
        baseline=2.0,
        improved=3.0,
        higher_is_better=True,
        delta_uncertainty=ComposedDeltaU95(u95_numerical=0.05),
        matched_conditions=True,
    )
    with pytest.raises(ValidationError, match="held_out"):
        OptimizationResult(
            objective="o",
            design_variables={},
            improvement=claim,
            cfd_verified=_prov(),
            n_candidates=15,
            held_out_verification=False,
        )

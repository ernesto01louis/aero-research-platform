"""Stage 16 — `IndependentDeltaU95` (ADR-029): measured, no-cancellation unsteady delta U95.

When a matched time-averaged delta has no common cycle basis (steady baseline vs a candidate
with resolved unsteadiness), the ADR-023 paired estimator is category-inapplicable. The
independent composition RSSes the two MEASURED sampling terms — conservative (claims no
cancellation), machine-measured (thesis-grade admissible), and still structurally excludes
hand-entered totals.
"""

from __future__ import annotations

import numpy as np
import pytest
from aero.provenance.four_fold import ProvenanceTuple
from aero.vv.reportable import (
    HandEnteredDeltaU95,
    ImprovementClaim,
    IndependentDeltaU95,
    OptimizationResult,
    ReportableQuantity,
    ReportableResult,
    SmallSignalError,
    StatisticalUncertainty,
)
from aero.vv.reportable_compose import compose_independent_improvement
from aero.vv.statistical_uncertainty import statistical_uncertainty_from_samples
from pydantic import ValidationError

pytestmark = pytest.mark.stage_16


def _prov() -> ProvenanceTuple:
    return ProvenanceTuple(
        git_sha="a" * 40,
        dvc_input_hash="0" * 64,
        container_sif_sha256="1" * 64,
        config_hash="2" * 64,
    )


def _reliable_stat(mean: float, scale: float, seed: int) -> StatisticalUncertainty:
    su = statistical_uncertainty_from_samples(
        np.random.default_rng(seed).normal(mean, scale, 35), amp_scale=5 * scale
    )
    assert su.reliable
    return su


def _unreliable_stat() -> StatisticalUncertainty:
    su = statistical_uncertainty_from_samples(np.cos(np.linspace(0.0, np.pi, 60)))
    assert not su.reliable
    return su


def test_rss_composition() -> None:
    b = _reliable_stat(20.0, 0.05, 0)
    c = _reliable_stat(45.0, 0.20, 1)
    du = IndependentDeltaU95(u95_numerical=1.5, baseline_stat=b, candidate_stat=c, u95_input=0.3)
    stat = (b.u95_statistical**2 + c.u95_statistical**2) ** 0.5
    assert du.u95_delta_statistical == pytest.approx(stat)
    assert du.u95_delta == pytest.approx((1.5**2 + stat**2 + 0.3**2) ** 0.5)


def test_steady_claim_with_independent_u95_is_category_error() -> None:
    du = IndependentDeltaU95(
        u95_numerical=1.0,
        baseline_stat=_reliable_stat(20.0, 0.05, 0),
        candidate_stat=_reliable_stat(45.0, 0.2, 1),
    )
    with pytest.raises(ValueError, match="category error"):
        ImprovementClaim(
            quantity="lift_to_drag",
            kind="steady",
            baseline=20.0,
            improved=45.0,
            higher_is_better=True,
            delta_uncertainty=du,
            matched_conditions=True,
        )


def test_small_signal_refused() -> None:
    with pytest.raises((ValidationError, SmallSignalError), match="not thesis-grade"):
        compose_independent_improvement(
            quantity="lift_to_drag",
            kind="time_averaged",
            higher_is_better=True,
            u95_delta_numerical=20.0,  # delta 25 <= 2*20
            baseline_stat=_reliable_stat(20.0, 0.05, 0),
            candidate_stat=_reliable_stat(45.0, 0.2, 1),
            baseline=20.0,
            improved=45.0,
        )


def test_compose_independent_rejects_steady_kind() -> None:
    with pytest.raises(ValueError, match="time/phase"):
        compose_independent_improvement(
            quantity="lift_to_drag",
            kind="steady",
            higher_is_better=True,
            u95_delta_numerical=1.0,
            baseline_stat=_reliable_stat(20.0, 0.05, 0),
            candidate_stat=_reliable_stat(45.0, 0.2, 1),
            baseline=20.0,
            improved=45.0,
        )


def _result(claim: ImprovementClaim, *, tag: str) -> ReportableResult:
    q = ReportableQuantity(
        name="lift_to_drag",
        value=claim.improved,
        kind="time_averaged",
        u95_numerical=1.0,
        u95_statistical=0.1,
    )
    opt = OptimizationResult(
        objective="maximize lift_to_drag (URANS time-averaged)",
        design_variables={"max_camber": 0.0727},
        improvement=claim,
        cfd_verified=_prov(),
        surrogate_predicted=True,
        n_candidates=14,
        held_out_verification=True,
    )
    return ReportableResult(
        case_name="airfoil_opt_naca4",
        quantities=(q,),
        provenance=_prov(),
        optimization=opt,
        validation_tag=tag,  # type: ignore[arg-type]
    )


def _claim(b_stat: StatisticalUncertainty, c_stat: StatisticalUncertainty) -> ImprovementClaim:
    return compose_independent_improvement(
        quantity="lift_to_drag",
        kind="time_averaged",
        higher_is_better=True,
        u95_delta_numerical=1.5,
        baseline_stat=b_stat,
        candidate_stat=c_stat,
        baseline=float(b_stat.mean),
        improved=float(c_stat.mean),
    )


def test_thesis_grade_accepts_reliable_independent() -> None:
    claim = _claim(_reliable_stat(20.0, 0.05, 0), _reliable_stat(45.0, 0.2, 1))
    result = _result(claim, tag="thesis-grade")
    assert result.validation_tag == "thesis-grade"


def test_thesis_grade_rejects_unreliable_independent() -> None:
    b = _reliable_stat(20.0, 0.05, 0)
    c = _unreliable_stat()
    du = IndependentDeltaU95(u95_numerical=1.5, baseline_stat=b, candidate_stat=c)
    claim = ImprovementClaim(
        quantity="lift_to_drag",
        kind="time_averaged",
        baseline=float(b.mean),
        improved=float(b.mean) + 25.0,
        higher_is_better=True,
        delta_uncertainty=du,
        matched_conditions=True,
    )
    with pytest.raises(ValueError, match="RELIABLE sampling estimates"):
        _result(claim, tag="thesis-grade")


def test_thesis_grade_still_rejects_hand_entered() -> None:
    claim = ImprovementClaim(
        quantity="lift_to_drag",
        kind="time_averaged",
        baseline=20.0,
        improved=45.0,
        higher_is_better=True,
        delta_uncertainty=HandEnteredDeltaU95(u95_delta=1.0),
        matched_conditions=True,
    )
    with pytest.raises(ValueError, match="MEASURED delta uncertainty"):
        _result(claim, tag="thesis-grade")

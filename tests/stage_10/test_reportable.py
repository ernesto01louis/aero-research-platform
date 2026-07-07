"""Stage 10 — the output-validity-bar schema (CONSTITUTION Invariant 10).

Pins the contract: RSS U95 composition, the improvement-exceeds-uncertainty gate,
the matched-condition requirement, the CFD-verified-optimum selection-bias guard,
and the thesis-grade gate on ReportableResult.
"""

from __future__ import annotations

import math

import pytest
from aero.provenance.four_fold import ProvenanceTuple
from aero.vv.reportable import (
    HandEnteredDeltaU95,
    ImprovementClaim,
    OptimizationResult,
    ReportableQuantity,
    ReportableResult,
    SmallSignalError,
    ValidationAnchor,
)
from pydantic import ValidationError


def _prov() -> ProvenanceTuple:
    return ProvenanceTuple(
        git_sha="a" * 40,
        dvc_input_hash="0" * 64,
        container_sif_sha256="1" * 64,
        config_hash="2" * 64,
    )


def _anchor(passed: bool = True) -> ValidationAnchor:
    return ValidationAnchor(
        reference="Dickinson 1999 Robofly",
        citation="Dickinson, Lehmann & Sane, Science 284 (1999) 1954-1960",
        tolerance=0.05,
        observed_error=0.03 if passed else 0.09,
        passed=passed,
    )


# --- U95 composition -------------------------------------------------------


def test_u95_total_is_root_sum_square() -> None:
    q = ReportableQuantity(
        name="cd", value=0.01, u95_numerical=3.0, u95_statistical=4.0, u95_input=12.0
    )
    assert q.u95_total == pytest.approx(13.0)  # 3-4-... 3^2+4^2+12^2 = 169


def test_u95_total_defaults_steady_to_numerical_only() -> None:
    q = ReportableQuantity(name="cd", value=0.01, u95_numerical=0.0005)
    assert q.u95_total == pytest.approx(0.0005)


def test_negative_u95_rejected() -> None:
    with pytest.raises(ValidationError):
        ReportableQuantity(name="cd", value=0.01, u95_numerical=-1.0)


# --- ImprovementClaim: improvement-exceeds-uncertainty ---------------------


def test_significant_improvement_constructs() -> None:
    claim = ImprovementClaim(
        quantity="propulsive_efficiency",
        kind="time_averaged",
        baseline=0.30,
        improved=0.40,
        higher_is_better=True,
        delta_uncertainty=HandEnteredDeltaU95(u95_delta=0.02),  # k*U95 = 0.04 < delta 0.10
        matched_conditions=True,
    )
    assert claim.delta == pytest.approx(0.10)
    assert claim.u95_delta == pytest.approx(0.02)
    assert claim.required_margin == pytest.approx(0.04)


def test_insignificant_improvement_rejected() -> None:
    # delta 0.03, k*U95 = 2*0.02 = 0.04 -> within noise -> not a claim
    with pytest.raises((SmallSignalError, ValidationError)):
        ImprovementClaim(
            quantity="propulsive_efficiency",
            kind="time_averaged",
            baseline=0.30,
            improved=0.33,
            higher_is_better=True,
            delta_uncertainty=HandEnteredDeltaU95(u95_delta=0.02),
            matched_conditions=True,
        )


def test_unmatched_conditions_rejected() -> None:
    with pytest.raises(ValidationError):
        ImprovementClaim(
            quantity="cd",
            kind="steady",
            baseline=0.0100,
            improved=0.0080,
            higher_is_better=False,  # lower cd is better -> delta = +0.0020
            delta_uncertainty=HandEnteredDeltaU95(u95_delta=0.0001),
            matched_conditions=False,
        )


def test_lower_is_better_direction() -> None:
    # cd reduced 0.0100 -> 0.0080: delta should read as +0.0020 (an improvement)
    claim = ImprovementClaim(
        quantity="cd",
        kind="steady",
        baseline=0.0100,
        improved=0.0080,
        higher_is_better=False,
        delta_uncertainty=HandEnteredDeltaU95(u95_delta=0.0005),  # k*U95 = 0.0010 < 0.0020
        matched_conditions=True,
    )
    assert claim.delta == pytest.approx(0.0020)


def test_k_below_one_rejected() -> None:
    with pytest.raises(ValidationError):
        ImprovementClaim(
            quantity="cd",
            kind="steady",
            baseline=0.01,
            improved=0.02,
            higher_is_better=True,
            delta_uncertainty=HandEnteredDeltaU95(u95_delta=0.001),
            k=0.5,
            matched_conditions=True,
        )


def test_kind_is_required_no_default() -> None:
    # a defaulted kind would let an unsteady delta silently skip the paired requirement
    with pytest.raises(ValidationError, match="kind"):
        ImprovementClaim(  # type: ignore[call-arg]
            quantity="cd",
            baseline=0.01,
            improved=0.02,
            higher_is_better=True,
            delta_uncertainty=HandEnteredDeltaU95(u95_delta=0.001),
            matched_conditions=True,
        )


# --- OptimizationResult: CFD-verified-optimum + selection bias --------------


def _claim() -> ImprovementClaim:
    return ImprovementClaim(
        quantity="propulsive_efficiency",
        kind="time_averaged",
        baseline=0.30,
        improved=0.40,
        higher_is_better=True,
        delta_uncertainty=HandEnteredDeltaU95(u95_delta=0.02),
        matched_conditions=True,
    )


def test_best_of_n_requires_held_out_verification() -> None:
    with pytest.raises(ValidationError):
        OptimizationResult(
            objective="maximize propulsive_efficiency at fixed thrust",
            design_variables={"stroke_amplitude_deg": 75.0, "pitch_timing": 0.1},
            improvement=_claim(),
            cfd_verified=_prov(),
            surrogate_predicted=True,
            n_candidates=64,
            held_out_verification=False,
        )


def test_single_candidate_optimum_ok() -> None:
    result = OptimizationResult(
        objective="maximize propulsive_efficiency at fixed thrust",
        design_variables={"stroke_amplitude_deg": 75.0},
        improvement=_claim(),
        cfd_verified=_prov(),
        n_candidates=1,
        held_out_verification=False,
    )
    assert result.improvement.delta > 0


# --- ReportableResult: the thesis-grade gate --------------------------------


def test_thesis_grade_requires_numerical_u95() -> None:
    q = ReportableQuantity(name="cd", value=0.01, u95_numerical=0.0)  # no GCI
    with pytest.raises(ValidationError):
        ReportableResult(
            case_name="naca0012",
            quantities=(q,),
            provenance=_prov(),
            anchors=(_anchor(passed=True),),
            validation_tag="thesis-grade",
        )


def test_thesis_grade_requires_anchor_or_verified_optimum() -> None:
    q = ReportableQuantity(name="cd", value=0.01, u95_numerical=0.0005)
    with pytest.raises(ValidationError):
        ReportableResult(
            case_name="naca0012",
            quantities=(q,),
            provenance=_prov(),
            anchors=(),  # no passing anchor, no optimization
            validation_tag="thesis-grade",
        )


def test_thesis_grade_happy_path_with_anchor() -> None:
    q = ReportableQuantity(name="cd", value=0.0081, u95_numerical=0.0002)
    result = ReportableResult(
        case_name="naca0012_verification",
        quantities=(q,),
        provenance=_prov(),
        anchors=(_anchor(passed=True),),
        validation_tag="thesis-grade",
    )
    assert result.validation_tag == "thesis-grade"


def test_smoke_tag_skips_the_gate() -> None:
    # smoke results are explicitly not publication-grade; no U95/anchor gate.
    q = ReportableQuantity(name="cd", value=0.01, u95_numerical=0.0)
    result = ReportableResult(
        case_name="smoke",
        quantities=(q,),
        provenance=_prov(),
        validation_tag="smoke",
    )
    assert result.validation_tag == "smoke"


def test_extra_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        ReportableQuantity(name="cd", value=0.01, u95_numerical=0.0001, bogus=1)  # type: ignore[call-arg]


def test_math_import_used() -> None:
    # guard the RSS helper against an accidental refactor to a wrong norm
    q = ReportableQuantity(name="x", value=0.0, u95_numerical=1.0, u95_statistical=1.0)
    assert q.u95_total == pytest.approx(math.sqrt(2.0))


# --- statistical-U95 enforcement (the GCI-only hole) ------------------------


def test_phase_averaged_thesis_grade_requires_statistical_u95() -> None:
    # a phase-averaged flapping quantity with no sampling uncertainty must NOT pass
    q = ReportableQuantity(
        name="thrust_coefficient",
        value=0.42,
        kind="phase_averaged",
        u95_numerical=0.01,
        u95_statistical=0.0,  # the hole: GCI present, sampling error missing
    )
    with pytest.raises(ValidationError, match="statistical U95"):
        ReportableResult(
            case_name="flapping_rigid",
            quantities=(q,),
            provenance=_prov(),
            anchors=(_anchor(passed=True),),
            validation_tag="thesis-grade",
        )


def test_time_averaged_thesis_grade_requires_statistical_u95() -> None:
    q = ReportableQuantity(
        name="cd", value=0.01, kind="time_averaged", u95_numerical=0.001, u95_statistical=0.0
    )
    with pytest.raises(ValidationError, match="statistical U95"):
        ReportableResult(
            case_name="unsteady",
            quantities=(q,),
            provenance=_prov(),
            anchors=(_anchor(passed=True),),
            validation_tag="thesis-grade",
        )


def test_phase_averaged_thesis_grade_ok_with_statistical_u95() -> None:
    q = ReportableQuantity(
        name="thrust_coefficient",
        value=0.42,
        kind="phase_averaged",
        u95_numerical=0.01,
        u95_statistical=0.008,
    )
    result = ReportableResult(
        case_name="flapping_rigid",
        quantities=(q,),
        provenance=_prov(),
        anchors=(_anchor(passed=True),),
        validation_tag="thesis-grade",
    )
    assert result.validation_tag == "thesis-grade"


def test_steady_quantity_needs_no_statistical_u95() -> None:
    # the default kind stays simple: a steady quantity is thesis-grade with GCI alone
    q = ReportableQuantity(name="cd", value=0.0081, u95_numerical=0.0002)
    assert q.kind == "steady"
    ReportableResult(
        case_name="naca0012",
        quantities=(q,),
        provenance=_prov(),
        anchors=(_anchor(passed=True),),
        validation_tag="thesis-grade",
    )


# --- u95_delta strictly positive; improvement/optimization mutually exclusive


def test_zero_u95_delta_rejected() -> None:
    # a zero-uncertainty delta would trivially clear any margin (gt=0 lives on the union arm)
    with pytest.raises(ValidationError):
        HandEnteredDeltaU95(u95_delta=0.0)
    with pytest.raises(ValidationError):
        ImprovementClaim(
            quantity="cd",
            kind="steady",
            baseline=0.0100,
            improved=0.0080,
            higher_is_better=False,
            delta_uncertainty=HandEnteredDeltaU95(u95_delta=0.0),
            matched_conditions=True,
        )


def test_improvement_and_optimization_mutually_exclusive() -> None:
    q = ReportableQuantity(name="propulsive_efficiency", value=0.40, u95_numerical=0.001)
    with pytest.raises(ValidationError, match="not both"):
        ReportableResult(
            case_name="flapping_opt",
            quantities=(q,),
            provenance=_prov(),
            improvement=_claim(),
            optimization=OptimizationResult(
                objective="maximize propulsive_efficiency at fixed thrust",
                design_variables={"stroke_amplitude_deg": 75.0},
                improvement=_claim(),
                cfd_verified=_prov(),
                n_candidates=1,
                held_out_verification=False,
            ),
            validation_tag="validated",
        )

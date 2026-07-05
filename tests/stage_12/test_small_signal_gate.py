"""small-signal-gate — CONSTITUTION Invariant 10 (IMPROVEMENT-EXCEEDS-UNCERTAINTY) enforcement.

The required ``small-signal-gate`` CI job runs this suite. It asserts that:

* a ``thesis-grade`` non-steady quantity cannot be constructed with ``u95_statistical == 0``
  (GCI alone is insufficient for an unsteady flow);
* an :class:`ImprovementClaim` whose delta does not exceed ``k * U95`` fails loud;
* the batch-means estimator produces a **positive, reliable** ``u95_statistical`` on a committed
  converged-cycle fixture — so a regression that zeroed the statistical term would turn this red;
* the full-U95 composer issues ``thesis-grade`` end-to-end when every condition holds.

Pure-host (numpy + pydantic), hermetic — no cluster.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aero.provenance.four_fold import ProvenanceTuple
from aero.vv.reportable import (
    ImprovementClaim,
    ReportableQuantity,
    ReportableResult,
    SmallSignalError,
    ValidationAnchor,
)
from aero.vv.reportable_compose import compose_reportable
from aero.vv.statistical_uncertainty import statistical_uncertainty_from_samples
from pydantic import ValidationError

pytestmark = pytest.mark.stage_12

_FIXTURE = Path(__file__).parent / "fixtures" / "converged_cycle_means.json"


def _prov() -> ProvenanceTuple:
    return ProvenanceTuple(
        git_sha="a" * 40,
        dvc_input_hash="0" * 64,
        container_sif_sha256="1" * 64,
        config_hash="2" * 64,
    )


def _passing_anchor() -> ValidationAnchor:
    return ValidationAnchor(
        reference="lock-in: response freq = forcing freq",
        citation="Placzek 2009; Koopmann 1967",
        tolerance=0.03,
        observed_error=0.006,
        passed=True,
    )


def test_thesis_grade_requires_positive_statistical_u95_for_nonsteady() -> None:
    q = ReportableQuantity(
        name="cd", value=1.0, kind="time_averaged", u95_numerical=0.02, u95_statistical=0.0
    )
    with pytest.raises(ValidationError, match="statistical U95"):
        ReportableResult(
            case_name="c",
            quantities=(q,),
            provenance=_prov(),
            anchors=(_passing_anchor(),),
            validation_tag="thesis-grade",
        )


def test_improvement_claim_rejects_insignificant_delta() -> None:
    # delta = 0.01 <= k*U95 = 2 * 0.02 = 0.04 -> not thesis-grade.
    with pytest.raises((ValidationError, SmallSignalError), match="not thesis-grade"):
        ImprovementClaim(
            quantity="propulsive_efficiency",
            baseline=1.0,
            improved=1.01,
            higher_is_better=True,
            u95_delta=0.02,
            matched_conditions=True,
        )


def test_improvement_claim_accepts_significant_delta() -> None:
    claim = ImprovementClaim(
        quantity="propulsive_efficiency",
        baseline=1.0,
        improved=1.20,
        higher_is_better=True,
        u95_delta=0.02,
        matched_conditions=True,
    )
    assert claim.delta > claim.required_margin


def test_batch_means_produces_positive_reliable_u95_on_fixture() -> None:
    data = json.loads(_FIXTURE.read_text())
    su = statistical_uncertainty_from_samples(data["per_cycle_mean"])
    assert su.u95_statistical > 0.0
    assert su.reliable


def test_compose_thesis_grade_end_to_end() -> None:
    data = json.loads(_FIXTURE.read_text())
    su = statistical_uncertainty_from_samples(data["per_cycle_mean"])
    result = compose_reportable(
        case_name="oscillating_cylinder_lockin",
        name="strouhal",
        value=0.1815,
        kind="phase_averaged",
        provenance=_prov(),
        u95_numerical=0.002,
        stat=su,
        u95_input_frac=0.01,
        anchor=_passing_anchor(),
    )
    assert result.validation_tag == "thesis-grade"
    q = result.quantities[0]
    assert q.u95_statistical > 0.0
    assert q.u95_total > 0.0

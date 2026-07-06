"""small-signal-gate — CONSTITUTION Invariant 10 (IMPROVEMENT-EXCEEDS-UNCERTAINTY) enforcement.

The required ``small-signal-gate`` CI job runs this suite. It asserts that:

* a ``thesis-grade`` non-steady quantity cannot be constructed with ``u95_statistical == 0``
  (GCI alone is insufficient for an unsteady flow);
* an :class:`ImprovementClaim` whose delta does not exceed ``k * U95`` fails loud;
* the batch-means estimator produces a **positive, reliable** ``u95_statistical`` on a committed
  converged-cycle fixture — so a regression that zeroed the statistical term would turn this red;
* the full-U95 composer issues ``thesis-grade`` end-to-end when every condition holds;
* **(review F1, ADR-023)** a hand-entered ``u95_delta`` can never reach ``thesis-grade`` — a
  publication claim's delta uncertainty must be COMPOSED from the paired-difference measurement
  (``aero/vv/paired_difference.py``), with a reliable difference-series estimate and a positive
  paired-numerical term — enforced on a committed paired fixture so a regression that re-opened
  the free-input hole would turn this red.

Pure-host (numpy + pydantic), hermetic — no cluster.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
from aero.provenance.four_fold import ProvenanceTuple
from aero.vv.paired_difference import (
    PairedDeltaUncertainty,
    paired_delta_uncertainty_from_samples,
)
from aero.vv.reportable import (
    ComposedDeltaU95,
    HandEnteredDeltaU95,
    ImprovementClaim,
    ReportableQuantity,
    ReportableResult,
    SmallSignalError,
    ValidationAnchor,
)
from aero.vv.reportable_compose import compose_improvement, compose_reportable
from aero.vv.statistical_uncertainty import statistical_uncertainty_from_samples
from pydantic import ValidationError

pytestmark = pytest.mark.stage_12

_FIXTURE = Path(__file__).parent / "fixtures" / "converged_cycle_means.json"
_PAIRED_FIXTURE = Path(__file__).parent / "fixtures" / "paired_cycle_means.json"


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
            kind="time_averaged",
            baseline=1.0,
            improved=1.01,
            higher_is_better=True,
            delta_uncertainty=HandEnteredDeltaU95(u95_delta=0.02),
            matched_conditions=True,
        )


def test_improvement_claim_accepts_significant_delta() -> None:
    claim = ImprovementClaim(
        quantity="propulsive_efficiency",
        kind="time_averaged",
        baseline=1.0,
        improved=1.20,
        higher_is_better=True,
        delta_uncertainty=HandEnteredDeltaU95(u95_delta=0.02),
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


# --- review F1 (ADR-023): u95_delta is COMPUTED, never trusted, at thesis grade -------------


def _paired_from_fixture() -> PairedDeltaUncertainty:
    data = json.loads(_PAIRED_FIXTURE.read_text())
    start = data["converged_from_cycle"]
    return paired_delta_uncertainty_from_samples(
        data["baseline"]["per_cycle_mean"][start:],
        data["candidate"]["per_cycle_mean"][start:],
        period=data["period"],
        pair_start=start,
    )


def _quantity_for_claim(paired: PairedDeltaUncertainty) -> ReportableQuantity:
    return ReportableQuantity(
        name="cd",
        value=paired.mean_candidate,
        kind="time_averaged",
        u95_numerical=0.004,
        u95_statistical=paired.candidate_stat.u95_statistical,
    )


def test_hand_entered_u95_delta_never_thesis_grade() -> None:
    """THE F1 tripwire: the claim constructs, but a thesis-grade result carrying it must not."""
    claim = ImprovementClaim(
        quantity="cd",
        kind="time_averaged",
        baseline=0.96,
        improved=0.90,
        higher_is_better=False,
        delta_uncertainty=HandEnteredDeltaU95(u95_delta=0.004),
        matched_conditions=True,
    )
    q = ReportableQuantity(
        name="cd", value=0.90, kind="time_averaged", u95_numerical=0.004, u95_statistical=0.002
    )
    with pytest.raises(ValidationError, match="hand-entered"):
        ReportableResult(
            case_name="paired",
            quantities=(q,),
            provenance=_prov(),
            anchors=(_passing_anchor(),),
            improvement=claim,
            validation_tag="thesis-grade",
        )
    # ... while a non-publication tier still accepts it (exploratory claims stay expressible).
    ReportableResult(
        case_name="paired",
        quantities=(q,),
        provenance=_prov(),
        anchors=(_passing_anchor(),),
        improvement=claim,
        validation_tag="validated",
    )


def test_composed_nonsteady_claim_requires_paired_measurement() -> None:
    with pytest.raises(ValidationError, match="paired-difference"):
        ImprovementClaim(
            quantity="cd",
            kind="time_averaged",
            baseline=0.96,
            improved=0.90,
            higher_is_better=False,
            delta_uncertainty=ComposedDeltaU95(u95_numerical=0.004),
            matched_conditions=True,
        )


def test_composed_steady_claim_forbids_paired_measurement() -> None:
    paired = _paired_from_fixture()
    with pytest.raises(ValidationError, match="category error"):
        ImprovementClaim(
            quantity="cd",
            kind="steady",
            baseline=paired.mean_baseline,
            improved=paired.mean_candidate,
            higher_is_better=False,
            delta_uncertainty=ComposedDeltaU95(u95_numerical=0.004, paired=paired),
            matched_conditions=True,
        )


def test_claim_values_must_come_from_the_paired_window() -> None:
    paired = _paired_from_fixture()
    with pytest.raises(ValidationError, match="SAME window"):
        ImprovementClaim(
            quantity="cd",
            kind="time_averaged",
            baseline=paired.mean_baseline + 0.01,  # value from a different window than the u95
            improved=paired.mean_candidate,
            higher_is_better=False,
            delta_uncertainty=ComposedDeltaU95(u95_numerical=0.004, paired=paired),
            matched_conditions=True,
        )


def test_unreliable_diff_stat_refused_thesis_grade_but_fine_validated() -> None:
    # A near-monotone difference series -> tiny N_eff -> diff_stat.reliable is False (the same
    # soft-flag doctrine as the single-series estimator; the schema gate is where it bites).
    rng = np.random.default_rng(21)
    n = 60
    b = 5.0 + rng.normal(0.0, 0.05, n)
    c = b + 0.5 + 0.05 * np.cos(np.linspace(0.0, np.pi, n))
    paired = paired_delta_uncertainty_from_samples(b, c, period=1.0)
    assert not paired.diff_stat.reliable
    claim = compose_improvement(
        quantity="cd",
        kind="time_averaged",
        higher_is_better=True,
        u95_delta_numerical=0.004,
        paired=paired,
    )
    q = ReportableQuantity(
        name="cd",
        value=paired.mean_candidate,
        kind="time_averaged",
        u95_numerical=0.004,
        u95_statistical=paired.candidate_stat.u95_statistical,
    )
    with pytest.raises(ValidationError, match="RELIABLE"):
        ReportableResult(
            case_name="paired",
            quantities=(q,),
            provenance=_prov(),
            anchors=(_passing_anchor(),),
            improvement=claim,
            validation_tag="thesis-grade",
        )
    ReportableResult(
        case_name="paired",
        quantities=(q,),
        provenance=_prov(),
        anchors=(_passing_anchor(),),
        improvement=claim,
        validation_tag="validated",
    )


def test_thesis_grade_composed_claim_requires_positive_paired_numerical() -> None:
    paired = _paired_from_fixture()
    claim = compose_improvement(
        quantity="cd",
        kind="time_averaged",
        higher_is_better=False,
        u95_delta_numerical=0.0,  # matched conditions reduce, never zero, discretization error
        paired=paired,
    )
    with pytest.raises(ValidationError, match="paired-numerical"):
        ReportableResult(
            case_name="paired",
            quantities=(_quantity_for_claim(paired),),
            provenance=_prov(),
            anchors=(_passing_anchor(),),
            improvement=claim,
            validation_tag="thesis-grade",
        )


def test_paired_fixture_measures_cancellation_and_composes_thesis_grade() -> None:
    """End-to-end on the committed paired fixture: estimator -> compose_improvement ->
    thesis-grade result. A regression that re-opened the F1 free-input hole, zeroed the
    paired term, or broke the RSS turns this red."""
    paired = _paired_from_fixture()
    assert paired.correlation > 0.8  # the fixture's shared component is measured
    assert paired.variance_reduction < 0.5  # cancellation measured, not assumed
    assert paired.diff_stat.reliable
    claim = compose_improvement(
        quantity="cd",
        kind="time_averaged",
        higher_is_better=False,
        u95_delta_numerical=0.004,
        paired=paired,
    )
    assert claim.u95_delta == pytest.approx(math.sqrt(0.004**2 + paired.u95_delta_statistical**2))
    result = ReportableResult(
        case_name="paired_fixture",
        quantities=(_quantity_for_claim(paired),),
        provenance=_prov(),
        anchors=(_passing_anchor(),),
        improvement=claim,
        validation_tag="thesis-grade",
    )
    assert result.validation_tag == "thesis-grade"


def test_small_signal_still_fires_through_the_composed_path() -> None:
    paired = _paired_from_fixture()
    # Inflate the paired-numerical term until k*U95 swallows the fixture's delta (~0.06).
    with pytest.raises((ValidationError, SmallSignalError), match="not thesis-grade"):
        compose_improvement(
            quantity="cd",
            kind="time_averaged",
            higher_is_better=False,
            u95_delta_numerical=0.05,
            paired=paired,
        )


def test_compose_improvement_rejects_explicit_values_for_nonsteady() -> None:
    paired = _paired_from_fixture()
    with pytest.raises(ValueError, match="SAME window"):
        compose_improvement(
            quantity="cd",
            kind="time_averaged",
            higher_is_better=False,
            u95_delta_numerical=0.004,
            paired=paired,
            baseline=0.96,
            improved=0.90,
        )


def test_compose_improvement_steady_requires_values_and_numerical() -> None:
    with pytest.raises(ValueError, match="explicit"):
        compose_improvement(
            quantity="cd",
            kind="steady",
            higher_is_better=False,
            u95_delta_numerical=0.004,
        )
    with pytest.raises(ValueError, match="positive"):
        compose_improvement(
            quantity="cd",
            kind="steady",
            higher_is_better=False,
            u95_delta_numerical=0.0,
            baseline=0.0100,
            improved=0.0080,
        )

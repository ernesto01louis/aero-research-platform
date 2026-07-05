"""Full-U95 composition (compose_reportable) — Stage 12 tag-resolution tests.

Exercises the conservative validation-tag policy: thesis-grade only with a positive numerical
U95, a positive + reliable statistical U95 (non-steady), and a passing anchor; anything short
downgrades to ``validated``. The failing-anchor case is exactly how an over-predicting case (a
documented CONCERN) is kept out of a publication tag without relaxing a tolerance.
"""

from __future__ import annotations

import math

import numpy as np
from aero.provenance.four_fold import ProvenanceTuple
from aero.vv.reportable import ValidationAnchor
from aero.vv.reportable_compose import compose_reportable, resolve_validation_tag
from aero.vv.statistical_uncertainty import (
    StatisticalUncertainty,
    statistical_uncertainty_from_samples,
)


def _prov() -> ProvenanceTuple:
    return ProvenanceTuple(
        git_sha="a" * 40,
        dvc_input_hash="0" * 64,
        container_sif_sha256="1" * 64,
        config_hash="2" * 64,
    )


def _reliable_stat() -> StatisticalUncertainty:
    su = statistical_uncertainty_from_samples(
        np.random.default_rng(0).normal(0.96, 0.02, 35), amp_scale=0.05
    )
    assert su.reliable
    return su


def _unreliable_stat() -> StatisticalUncertainty:
    su = statistical_uncertainty_from_samples(np.cos(np.linspace(0.0, np.pi, 60)))
    assert not su.reliable
    return su


def _anchor(passed: bool) -> ValidationAnchor:
    return (
        ValidationAnchor(
            reference="lock-in: response freq = forcing freq",
            citation="Placzek 2009; Koopmann 1967",
            tolerance=0.03,
            observed_error=0.006,
            passed=True,
        )
        if passed
        else ValidationAnchor(
            reference="Heathcote & Gursul 2007 rigid foil (primary-source ~0.2-0.3)",
            citation="Heathcote & Gursul, AIAA J 45(5) 2007",
            tolerance=0.15,
            observed_error=2.0,  # ~3x over-prediction -> fails the band
            passed=False,
        )
    )


def test_thesis_grade_when_all_conditions_hold() -> None:
    stat = _reliable_stat()
    result = compose_reportable(
        case_name="oscillating_cylinder_lockin",
        name="strouhal",
        value=0.1815,
        kind="phase_averaged",
        provenance=_prov(),
        u95_numerical=0.002,
        stat=stat,
        u95_input_frac=0.01,
        anchor=_anchor(passed=True),
    )
    assert result.validation_tag == "thesis-grade"
    q = result.quantities[0]
    assert q.u95_statistical == stat.u95_statistical
    assert q.u95_input == 0.01 * 0.1815
    expected = math.sqrt(q.u95_numerical**2 + q.u95_statistical**2 + q.u95_input**2)
    assert math.isclose(q.u95_total, expected)


def test_failing_anchor_downgrades_to_validated() -> None:
    """An over-predicting case (failing anchor) is a CONCERN, not thesis-grade — no relaxation."""
    result = compose_reportable(
        case_name="plunging_airfoil_hg2007",
        name="thrust_coefficient",
        value=0.96,
        kind="time_averaged",
        provenance=_prov(),
        u95_numerical=0.03,
        stat=_reliable_stat(),
        u95_input_frac=0.4,  # large reference/model uncertainty at St=0.4
        anchor=_anchor(passed=False),
    )
    assert result.validation_tag == "validated"


def test_unreliable_statistical_term_downgrades() -> None:
    result = compose_reportable(
        case_name="case",
        name="cd",
        value=1.0,
        kind="time_averaged",
        provenance=_prov(),
        u95_numerical=0.02,
        stat=_unreliable_stat(),
        anchor=_anchor(passed=True),
    )
    assert result.validation_tag == "validated"


def test_nonsteady_without_statistical_term_downgrades() -> None:
    result = compose_reportable(
        case_name="case",
        name="cd",
        value=1.0,
        kind="time_averaged",
        provenance=_prov(),
        u95_numerical=0.02,
        stat=None,  # no statistical term -> cannot be thesis-grade for a non-steady quantity
        anchor=_anchor(passed=True),
    )
    assert result.validation_tag == "validated"


def test_allow_thesis_grade_false_forces_validated() -> None:
    tag = resolve_validation_tag(
        compose_reportable(
            case_name="c",
            name="strouhal",
            value=0.18,
            kind="phase_averaged",
            provenance=_prov(),
            u95_numerical=0.002,
            stat=_reliable_stat(),
            anchor=_anchor(passed=True),
            allow_thesis_grade=False,
        ).quantities[0],
        stat=_reliable_stat(),
        anchor=_anchor(passed=True),
        allow_thesis_grade=False,
    )
    assert tag == "validated"

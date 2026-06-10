"""Stage 09 — surrogate-vs-CFD cross-check (aero/vv/surrogate)."""

from __future__ import annotations

import json

import pytest
from aero.vv.surrogate import SurrogateVVCase, compare_surrogate_cfd

from tests.stage_09._fakes import FakeSurrogate, make_cert

pytestmark = pytest.mark.stage_09

_TARGETS = ("cd", "cl", "clf", "clr", "cs")
_REF = (0.30, 0.05, 0.02, 0.03, 0.0)


def _cases(n: int, *, re: float | None = None) -> list[SurrogateVVCase]:
    return [
        SurrogateVVCase(
            case_id=f"c{i}",
            surface_input=(float(i),),
            reference=_REF,
            target_names=_TARGETS,
            re=re,
        )
        for i in range(n)
    ]


def test_perfect_prediction_passes() -> None:
    s = FakeSurrogate(make_cert(), prediction=_REF)
    report = compare_surrogate_cfd(s, _cases(5))
    assert report.cd_within_tolerance is True
    assert report.passed is True
    assert report.rmse["cd"] == pytest.approx(0.0)


def test_cd_error_above_tolerance_fails() -> None:
    pred = (0.40, 0.05, 0.02, 0.03, 0.0)  # ~33% Cd error
    s = FakeSurrogate(make_cert(), prediction=pred)
    report = compare_surrogate_cfd(s, _cases(5))
    assert report.cd_within_tolerance is False
    assert report.passed is False


def test_empty_cases_raises() -> None:
    s = FakeSurrogate(make_cert(), prediction=_REF)
    with pytest.raises(ValueError, match="no cases"):
        compare_surrogate_cfd(s, [])


def test_envelope_violation_fails_even_if_cd_ok() -> None:
    s = FakeSurrogate(make_cert(), prediction=_REF)
    # re = 2e7 is outside DRIVAER_ENVELOPE.re_range = (8e6, 1.1e7).
    report = compare_surrogate_cfd(s, _cases(3, re=2.0e7))
    assert report.cd_within_tolerance is True
    assert report.envelope_respected is False
    assert report.passed is False
    assert report.n_envelope_checked == 3


def test_report_json_and_markdown() -> None:
    s = FakeSurrogate(make_cert(), prediction=_REF)
    report = compare_surrogate_cfd(s, _cases(2))
    data = json.loads(report.to_json())
    assert data["passed"] is True
    assert data["model_architecture"] == "domino"
    assert "cd" in data["rmse"]
    assert report.to_markdown().startswith("# Surrogate V&V")

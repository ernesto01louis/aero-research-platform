"""Stage 14 — thesis-grade gate hardening (external-review P1b + P1d).

P1b: a ``-dirty`` provenance SHA can never be thesis-grade — the recorded SHA does not
describe what actually ran. P1d: ``u95_input_basis`` makes "input-UQ performed and found
negligible" distinguishable from "input-UQ skipped", so a thesis-grade result cannot
silently omit input uncertainty and read as though it had none.
"""

from __future__ import annotations

import pytest
from aero.provenance.four_fold import ProvenanceTuple
from aero.vv.reportable import (
    ComposedDeltaU95,
    ReportableQuantity,
    ReportableResult,
    ValidationAnchor,
)
from aero.vv.reportable_compose import compose_reportable
from pydantic import ValidationError


def _prov(*, dirty: bool = False) -> ProvenanceTuple:
    sha = "a" * 40 + ("-dirty" if dirty else "")
    return ProvenanceTuple(
        git_sha=sha,
        dvc_input_hash="0" * 64,
        container_sif_sha256="1" * 64,
        config_hash="2" * 64,
    )


def _anchor() -> ValidationAnchor:
    return ValidationAnchor(
        reference="WBD 2004 2-D",
        citation="Wang, Birch & Dickinson, J Exp Biol 207 (2004) 449-460",
        tolerance=0.20,
        observed_error=0.10,
        passed=True,
    )


def _thesis_quantity() -> ReportableQuantity:
    # A non-steady quantity that satisfies the numerical + statistical + anchor requirements.
    return ReportableQuantity(
        name="mean_lift_coefficient",
        value=1.0,
        kind="time_averaged",
        u95_numerical=0.02,
        u95_statistical=0.03,
        u95_input=0.05,
        u95_input_basis="estimated",
    )


# --- P1b: dirty SHA barred from thesis-grade --------------------------------


def test_clean_sha_thesis_grade_constructs() -> None:
    result = ReportableResult(
        case_name="flapping_wing_wbd2004",
        quantities=(_thesis_quantity(),),
        provenance=_prov(dirty=False),
        anchors=(_anchor(),),
        validation_tag="thesis-grade",
    )
    assert result.validation_tag == "thesis-grade"


def test_dirty_sha_rejected_at_thesis_grade() -> None:
    with pytest.raises(ValidationError, match="dirty"):
        ReportableResult(
            case_name="flapping_wing_wbd2004",
            quantities=(_thesis_quantity(),),
            provenance=_prov(dirty=True),
            anchors=(_anchor(),),
            validation_tag="thesis-grade",
        )


def test_dirty_sha_allowed_below_thesis_grade() -> None:
    # A dirty tree is fine for exploratory/validated results — the gate only bites thesis-grade.
    result = ReportableResult(
        case_name="flapping_wing_wbd2004",
        quantities=(_thesis_quantity(),),
        provenance=_prov(dirty=True),
        anchors=(_anchor(),),
        validation_tag="validated",
    )
    assert result.validation_tag == "validated"


# --- P1d: input-UQ basis distinguishes performed-negligible from skipped ----


def test_skipped_basis_requires_zero_input() -> None:
    with pytest.raises(ValidationError, match="skipped"):
        ReportableQuantity(
            name="cd",
            value=1.0,
            u95_numerical=0.01,
            u95_input=0.02,
            u95_input_basis="skipped",
        )


def test_default_basis_is_skipped_and_zero_is_consistent() -> None:
    q = ReportableQuantity(name="cd", value=1.0, u95_numerical=0.01)
    assert q.u95_input_basis == "skipped"
    assert q.u95_input == 0.0


@pytest.mark.parametrize("basis", ["measured", "estimated"])
def test_performed_but_negligible_is_allowed(basis: str) -> None:
    # "performed and found ~0" is the state P1d exists to preserve — must be constructible.
    q = ReportableQuantity(
        name="cd", value=1.0, u95_numerical=0.01, u95_input=0.0, u95_input_basis=basis
    )
    assert q.u95_input_basis == basis
    assert q.u95_input == 0.0


def test_compose_reportable_auto_resolves_estimated_from_nonzero_fraction() -> None:
    # A nonzero input fraction must never be silently recorded as 'skipped'.
    result = compose_reportable(
        case_name="c",
        name="mean_lift_coefficient",
        value=1.0,
        kind="time_averaged",
        provenance=_prov(),
        u95_numerical=0.02,
        u95_input_frac=0.05,
        allow_thesis_grade=False,
    )
    q = result.quantities[0]
    assert q.u95_input == pytest.approx(0.05)
    assert q.u95_input_basis == "estimated"


def test_compose_reportable_zero_fraction_defaults_skipped() -> None:
    result = compose_reportable(
        case_name="c",
        name="cd",
        value=1.0,
        kind="steady",
        provenance=_prov(),
        u95_numerical=0.01,
    )
    q = result.quantities[0]
    assert q.u95_input == 0.0
    assert q.u95_input_basis == "skipped"


def test_compose_reportable_explicit_basis_is_respected() -> None:
    result = compose_reportable(
        case_name="c",
        name="cd",
        value=1.0,
        kind="steady",
        provenance=_prov(),
        u95_numerical=0.01,
        u95_input_frac=0.0,
        u95_input_basis="measured",
    )
    assert result.quantities[0].u95_input_basis == "measured"


# --- thesis-grade composed-delta result still round-trips with a clean SHA ---


def test_composed_delta_result_unaffected_by_hardening() -> None:
    # A ComposedDeltaU95 steady claim (paired omitted) with a clean SHA is unchanged by P1b/P1d.
    du = ComposedDeltaU95(u95_numerical=0.001)
    assert du.u95_delta == pytest.approx(0.001)

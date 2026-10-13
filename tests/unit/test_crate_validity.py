"""A crate cannot claim more than its content supports (ADR-047 D4)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from aero.crate import CrateError, build_crate
from aero.crate.model import RunRecord
from aero.crate.validity import GateVerdict, Limitation, ValidityContext, Verdict
from pydantic import ValidationError

from tests.unit._crate_fixtures import (
    ADR047,
    SHAPES,
    available_run,
    evidence_only,
    four_tuple,
    lim,
    steady_optimization,
    thesis_grade_paired,
)

pytestmark = pytest.mark.stage_21


def _without(spec, limitation_id: str):  # type: ignore[no-untyped-def]
    v = spec.validity
    kept = tuple(x for x in v.limitations if x.id != limitation_id)
    return replace(spec, validity=v.model_copy(update={"limitations": kept}))


@pytest.mark.parametrize(
    ("shape", "limitation"),
    [
        ("steady_optimization", "not-flagship-domain"),
        ("steady_optimization", "no-experiment-anchor"),
        ("steady_optimization", "input-uq-skipped"),
        ("steady_optimization", "dvc-input-hash-sync-state"),
        ("steady_optimization", "container-digest-by-lookup"),
        ("steady_optimization", "provenance-sha-not-public"),
        ("evidence_only", "nogo"),
        ("evidence_only", "diagnostic-not-gate"),
        ("evidence_only", "provenance-unavailable"),
        ("evidence_only", "no-claim"),
    ],
)
def test_every_mandatory_limitation_is_enforced(shape: str, limitation: str) -> None:
    with pytest.raises(CrateError, match="required limitations"):
        build_crate(_without(SHAPES[shape](), limitation))


def test_the_flagship_limitation_must_quote_adr046_s3() -> None:
    spec = steady_optimization()
    lims = tuple(
        lim("not-flagship-domain", "airfoil only") if x.id == "not-flagship-domain" else x
        for x in spec.validity.limitations
    )
    with pytest.raises(CrateError, match="ADR-046 S3"):
        build_crate(replace(spec, validity=spec.validity.model_copy(update={"limitations": lims})))


def test_the_claim_tier_must_be_the_result_tag() -> None:
    spec = steady_optimization()
    with pytest.raises(CrateError, match="claim_tier"):
        build_crate(
            replace(spec, validity=spec.validity.model_copy(update={"claim_tier": "thesis-grade"}))
        )


def test_experiment_validation_is_rederived_from_the_anchors() -> None:
    spec = thesis_grade_paired()
    with pytest.raises(CrateError, match="validated_against_experiment"):
        build_crate(
            replace(
                spec,
                validity=spec.validity.model_copy(update={"validated_against_experiment": False}),
            )
        )


def test_an_evidence_only_crate_cannot_carry_a_go() -> None:
    spec = evidence_only()
    gate = GateVerdict(
        name="ok",
        gated=True,
        criterion="x <= 1",
        comparator="le",
        threshold=1.0,
        observed=0.5,
        passed=True,
        preregistered_in=ADR047,
    )
    verdicts = (*spec.validity.verdicts, Verdict(scope="speed-up", overall="GO", gates=(gate,)))
    with pytest.raises(CrateError, match="GO"):
        build_crate(replace(spec, validity=spec.validity.model_copy(update={"verdicts": verdicts})))


def test_gate_and_verdict_arithmetic_is_rederived() -> None:
    with pytest.raises(ValidationError, match="contradicts"):
        GateVerdict(
            name="g",
            gated=False,
            criterion="c",
            comparator="gt",
            threshold=1.0,
            observed=0.5,
            passed=True,
        )
    with pytest.raises(ValidationError, match="pre-registration"):
        GateVerdict(
            name="g",
            gated=True,
            criterion="c",
            comparator="gt",
            threshold=1.0,
            observed=2.0,
            passed=True,
        )
    good = GateVerdict(
        name="g",
        gated=True,
        criterion="c",
        comparator="within",
        threshold=(0.5, 2.0),
        observed=0.4,
        passed=False,
        preregistered_in=ADR047,
    )
    with pytest.raises(ValidationError, match="gates say NO-GO"):
        Verdict(scope="grid-certification", overall="GO", gates=(good,))
    diag = GateVerdict(
        name="d",
        gated=False,
        criterion="c",
        comparator="is-true",
        threshold=None,
        observed=True,
        passed=True,
    )
    with pytest.raises(ValidationError, match="no gated gate"):
        Verdict(scope="speed-up", overall="GO", gates=(diag,))


def test_design_variables_must_lie_inside_the_declared_bounds() -> None:
    spec = steady_optimization()
    with pytest.raises(CrateError, match="outside"):
        build_crate(
            replace(
                spec,
                validity=spec.validity.model_copy(
                    update={
                        "design_space": {"max_camber": (0.0, 0.05), "camber_position": (0.2, 0.6)}
                    }
                ),
            )
        )
    with pytest.raises(CrateError, match="no applicability bound"):
        build_crate(
            replace(
                spec,
                validity=spec.validity.model_copy(
                    update={"design_space": {"max_camber": (0.0, 0.08)}}
                ),
            )
        )


def test_every_available_run_needs_its_config_preimage() -> None:
    spec = steady_optimization()
    with pytest.raises(CrateError, match="config preimages"):
        build_crate(replace(spec, configs=()))


def test_every_container_digest_needs_a_reference() -> None:
    spec = steady_optimization()
    refs = tuple(r for r in spec.references if r.role != "container")
    with pytest.raises(CrateError, match="container"):
        build_crate(replace(spec, references=refs))


def test_the_record_of_provenance_must_be_the_result_provenance() -> None:
    spec = thesis_grade_paired()
    other = four_tuple({"name": "something else"})
    run: RunRecord = available_run("other", 9, other, ("record-of-provenance",))
    with pytest.raises(CrateError):
        build_crate(replace(spec, runs=(run,), configs=({"name": "something else"},)))


def test_a_run_without_a_four_tuple_cannot_be_the_record() -> None:
    spec = evidence_only()
    data = spec.runs[0].model_dump()
    data["roles"] = ("record-of-provenance",)
    with pytest.raises(ValidationError, match="cannot be the record"):
        RunRecord.model_validate(data)


def test_limitation_ids_are_a_closed_vocabulary() -> None:
    with pytest.raises(ValidationError):
        Limitation.model_validate(
            {"id": "anything-goes", "kind": "statement", "text": "x", "source": ADR047}
        )
    with pytest.raises(ValidationError, match="twice"):
        ValidityContext(
            claim_tier="smoke",
            claim_scope="uq-reference",
            flagship_domain=False,
            validated_against_experiment=False,
            limitations=(lim("nogo"), lim("nogo")),
        )


def test_a_quote_must_be_verbatim() -> None:
    spec = evidence_only()
    lims = tuple(
        x.model_copy(update={"text": '"verdict": "GO"'}) if x.kind == "quote" else x
        for x in spec.validity.limitations
    )
    with pytest.raises(CrateError, match="verbatim"):
        build_crate(replace(spec, validity=spec.validity.model_copy(update={"limitations": lims})))

"""Compose a full-``U95`` :class:`~aero.vv.reportable.ReportableResult` for one reported quantity.

Stage 12 wires the three independent U95 contributions into the live thesis-grade contract:

* ``u95_numerical`` — the GCI / ASME V&V 20 discretization uncertainty. The mesh-sweep
  (:mod:`aero.vv.mesh_sweep`) reports it as a *fraction*; the caller multiplies by ``|value|``
  and passes it here as an absolute (this module stays free of the heavy runner imports so
  ``aero`` core keeps importing with no extras — PLATFORM-NOT-HUB).
* ``u95_statistical`` — the batch-means sampling uncertainty
  (:class:`aero.vv.statistical_uncertainty.StatisticalUncertainty`).
* ``u95_input`` — the parametric / reference-digitization uncertainty, given as a fraction of
  ``|value|``.

The **validation tag** is resolved conservatively: ``thesis-grade`` is issued only when every
thesis-grade condition holds — a positive numerical U95, a positive *and* ``reliable`` statistical
U95 for a non-steady quantity, and a passing experiment anchor. Any shortfall downgrades to
``validated`` (not publication-grade). This is where an *unreliable* batch-means term or a failing
validation (e.g. an over-predicting case) is refused a publication tag — the "STOP" for
CONSTITUTION Invariant 10 lives here, not as a hard crash in the estimator.

Strict pydantic all the way down; stdlib + numpy + pydantic only.
"""

from __future__ import annotations

from aero.provenance.four_fold import ProvenanceTuple
from aero.vv.reportable import (
    QuantityKind,
    ReportableQuantity,
    ReportableResult,
    ValidationAnchor,
    ValidationTag,
)
from aero.vv.statistical_uncertainty import StatisticalUncertainty


def resolve_validation_tag(
    quantity: ReportableQuantity,
    *,
    stat: StatisticalUncertainty | None,
    anchor: ValidationAnchor | None,
    allow_thesis_grade: bool = True,
) -> ValidationTag:
    """Pick the highest tag the evidence supports (``thesis-grade`` -> ``validated``).

    ``thesis-grade`` requires: numerical U95 > 0; for a non-steady quantity a positive statistical
    U95 from a ``reliable`` estimate; and a passing experiment anchor. This mirrors
    :meth:`ReportableResult._thesis_grade_gate` and adds the estimator-reliability policy the schema
    cannot see. Anything short downgrades to ``validated``.
    """
    if not allow_thesis_grade:
        return "validated"
    if quantity.u95_numerical <= 0.0:
        return "validated"
    if quantity.kind != "steady":
        if quantity.u95_statistical <= 0.0:
            return "validated"
        if stat is not None and not stat.reliable:
            return "validated"
    if anchor is None or not anchor.passed:
        return "validated"
    return "thesis-grade"


def compose_reportable(
    *,
    case_name: str,
    name: str,
    value: float,
    kind: QuantityKind,
    provenance: ProvenanceTuple,
    units: str = "",
    u95_numerical: float = 0.0,
    stat: StatisticalUncertainty | None = None,
    u95_input_frac: float = 0.0,
    anchor: ValidationAnchor | None = None,
    allow_thesis_grade: bool = True,
) -> ReportableResult:
    """Assemble a single-quantity :class:`ReportableResult` with its RSS-composed ``U95``.

    ``u95_numerical`` is an absolute value (GCI fraction already multiplied by ``|value|``);
    ``u95_input_frac`` is a fraction of ``|value|``; ``stat`` supplies the absolute statistical
    U95. The tag is resolved by :func:`resolve_validation_tag`; the returned ``ReportableResult``
    re-validates the thesis-grade contract on construction (fail-loud).
    """
    quantity = ReportableQuantity(
        name=name,
        value=value,
        units=units,
        kind=kind,
        u95_numerical=u95_numerical,
        u95_statistical=stat.u95_statistical if stat is not None else 0.0,
        u95_input=abs(u95_input_frac) * abs(value),
    )
    tag = resolve_validation_tag(
        quantity, stat=stat, anchor=anchor, allow_thesis_grade=allow_thesis_grade
    )
    anchors = (anchor,) if anchor is not None else ()
    return ReportableResult(
        case_name=case_name,
        quantities=(quantity,),
        provenance=provenance,
        anchors=anchors,
        validation_tag=tag,
    )

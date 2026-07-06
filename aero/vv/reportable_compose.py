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

:func:`compose_improvement` (review F1; ADR-023) is the delta-side sibling: it assembles a
:class:`~aero.vv.reportable.ComposedDeltaU95` from the paired-difference measurement
(:mod:`aero.vv.paired_difference`) plus the caller's GCI-on-the-delta, and constructs the
:class:`~aero.vv.reportable.ImprovementClaim` — whose validators refuse an insignificant delta
(``SmallSignalError``) at construction. The RSS itself lives in the schema's computed field.

Strict pydantic all the way down; stdlib + numpy + pydantic only.
"""

from __future__ import annotations

from aero.provenance.four_fold import ProvenanceTuple
from aero.vv.paired_difference import PairedDeltaUncertainty
from aero.vv.reportable import (
    DEFAULT_K,
    ComposedDeltaU95,
    ImprovementClaim,
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


def compose_improvement(
    *,
    quantity: str,
    kind: QuantityKind,
    higher_is_better: bool,
    u95_delta_numerical: float,
    paired: PairedDeltaUncertainty | None = None,
    baseline: float | None = None,
    improved: float | None = None,
    u95_delta_input_frac: float = 0.0,
    k: float = DEFAULT_K,
    matched_conditions: bool = True,
) -> ImprovementClaim:
    """Assemble a composed :class:`ImprovementClaim` with its measured, RSS-combined ``u95_delta``.

    The delta-side sibling of :func:`compose_reportable` (review F1; ADR-023), with the same
    seam: ``u95_delta_numerical`` arrives ABSOLUTE (the caller forms the GCI-on-the-delta /
    matched-grid-Richardson bound — this module stays free of runner imports); the statistical
    term arrives as the typed paired-difference measurement; the input term arrives as a
    fraction.

    * **Non-steady** (``time_averaged`` / ``phase_averaged``): ``paired`` is REQUIRED and
      ``baseline`` / ``improved`` are taken **from** the paired-window means — passing them
      explicitly raises, so the claimed values and the measured uncertainty cannot come from
      different windows.
    * **Steady:** no per-cycle series exists, so ``paired`` must be omitted; ``baseline`` /
      ``improved`` are required and ``u95_delta_numerical`` must be positive (a steady delta's
      only measured term is the paired-numerical one).

    ``u95_delta_input_frac`` is a fraction of ``|baseline|`` — NOT of the delta (that would
    shrink the bar exactly as the claim shrinks — anti-conservative and circular). For a
    matched pair the common-mode input error largely cancels: pass only the defensible
    *residual* sensitivity-difference fraction, not the absolute-quantity input fraction used
    for single-value results.

    The RSS composition lives in :class:`ComposedDeltaU95.u95_delta` (a computed field — no
    free total to mistype); ``SmallSignalError`` fires inside :class:`ImprovementClaim`'s own
    validator if the delta does not clear ``k * u95_delta`` — constructing a claim IS the claim.
    """
    if kind == "steady":
        if paired is not None:
            raise ValueError(
                "compose_improvement: a steady claim has no per-cycle series — omit `paired` "
                "(or fix `kind` if the quantity is a time/phase-average)."
            )
        if baseline is None or improved is None:
            raise ValueError(
                "compose_improvement: a steady claim requires explicit `baseline` and "
                "`improved` values (there is no paired window to take them from)."
            )
        if u95_delta_numerical <= 0.0:
            raise ValueError(
                "compose_improvement: a steady claim's only measured term is the paired-"
                "numerical one — u95_delta_numerical must be positive (GCI on the delta / "
                "matched-grid Richardson)."
            )
        baseline_value, improved_value = baseline, improved
    else:
        if paired is None:
            raise ValueError(
                f"compose_improvement: a {kind} claim requires the paired-difference "
                "measurement (aero.vv.paired_difference.paired_delta_uncertainty) — the "
                "statistical term of an unsteady delta is measured, never asserted "
                "(Invariant 10, ADR-023)."
            )
        if baseline is not None or improved is not None:
            raise ValueError(
                "compose_improvement: for a non-steady claim, `baseline`/`improved` are taken "
                "FROM the paired-window means — do not pass them explicitly (the value and its "
                "uncertainty must come from the SAME window)."
            )
        baseline_value, improved_value = paired.mean_baseline, paired.mean_candidate

    delta_uncertainty = ComposedDeltaU95(
        u95_numerical=u95_delta_numerical,
        paired=paired,
        u95_input=abs(u95_delta_input_frac) * abs(baseline_value),
    )
    return ImprovementClaim(
        quantity=quantity,
        kind=kind,
        baseline=baseline_value,
        improved=improved_value,
        higher_is_better=higher_is_better,
        delta_uncertainty=delta_uncertainty,
        k=k,
        matched_conditions=matched_conditions,
    )

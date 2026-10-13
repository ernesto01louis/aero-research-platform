"""Cross-file rules and REQUIRED limitations (ADR-047 D4). Run by the writer and the reader.

A crate cannot claim more than its content supports. :func:`check_validity` couples the
envelope's validity context to the payload and the runs, and derives the limitations the content
makes **mandatory**. A crate that, for example, carries an optimization without an
experiment-anchored forward model, but omits ``no-experiment-anchor``, is refused.
"""

from __future__ import annotations

from aero.crate.errors import CrateSemanticError
from aero.crate.model import CrateManifest, ProvenanceAvailable
from aero.crate.validity import CORE_UNAVAILABLE, FLAGSHIP_LIMITATION_SENTENCE
from aero.vv.reportable import ReportableResult

__all__ = ["check_validity", "required_limitations"]


def required_limitations(manifest: CrateManifest, result: ReportableResult | None) -> set[str]:
    """The limitation ids the crate's own content makes mandatory."""
    need: set[str] = set()
    v = manifest.validity
    if result is not None:
        if any(q.u95_input_basis == "skipped" for q in result.quantities):
            need.add("input-uq-skipped")
        if not any(a.passed for a in result.anchors):
            need.add("no-experiment-anchor")
    if any(verdict.overall == "NO-GO" for verdict in v.verdicts):
        need.add("nogo")
    if any(not g.gated for verdict in v.verdicts for g in verdict.gates):
        need.add("diagnostic-not-gate")
    unavailable_runs = [
        r for r in manifest.runs if not isinstance(r.provenance, ProvenanceAvailable)
    ]
    if unavailable_runs or any(u.item in CORE_UNAVAILABLE for u in manifest.unavailable):
        need.add("provenance-unavailable")
    available = [
        r.provenance for r in manifest.runs if isinstance(r.provenance, ProvenanceAvailable)
    ]
    if any(not p.code.publicly_resolvable for p in available):
        need.add("provenance-sha-not-public")
    if available:
        need.update({"dvc-input-hash-sync-state", "container-digest-by-lookup"})
    if v.certificate_expiry is not None:
        need.add("certificate-expiry")
    if v.claim_scope == "optimization" and not v.flagship_domain:
        need.add("not-flagship-domain")
    if v.claim_tier == "none":
        need.add("no-claim")
    return need


def check_validity(
    manifest: CrateManifest,
    result: ReportableResult | None,
    config_hashes: set[str],
) -> None:
    """Raise :class:`CrateSemanticError` unless every cross-file rule holds."""
    v = manifest.validity
    core_missing = {u.item for u in manifest.unavailable} & CORE_UNAVAILABLE

    # Payload <-> tier <-> declared absences.
    if manifest.payload == "none":
        if result is not None:
            raise CrateSemanticError("an evidence-only crate carries no result")
        if v.claim_tier != "none":
            raise CrateSemanticError("an evidence-only crate has claim_tier 'none'")
        if not core_missing:
            raise CrateSemanticError(
                "an evidence-only crate must declare which core component (four_tuple, u95, "
                "case_spec) is unavailable"
            )
        if any(verdict.overall == "GO" for verdict in v.verdicts):
            raise CrateSemanticError("an evidence-only crate cannot carry a GO verdict")
    else:
        if result is None:
            raise CrateSemanticError("a reportable-result crate carries a result")
        if core_missing:
            raise CrateSemanticError(
                f"a crate with a result cannot declare core components unavailable: {sorted(core_missing)}"
            )
        if v.claim_tier != result.validation_tag:
            raise CrateSemanticError(
                f"claim_tier {v.claim_tier!r} != result.validation_tag {result.validation_tag!r}"
            )
        if v.validated_against_experiment != any(a.passed for a in result.anchors):
            raise CrateSemanticError(
                "validated_against_experiment contradicts the result's anchors"
            )
        records = [r for r in manifest.runs if "record-of-provenance" in r.roles]
        if len(records) != 1:
            raise CrateSemanticError("exactly one run must be the record of provenance")
        record = records[0].provenance
        assert isinstance(record, ProvenanceAvailable)  # RunRecord forbids otherwise
        if record.four_tuple != result.provenance:
            raise CrateSemanticError(
                "the record-of-provenance run's four-tuple != result.provenance"
            )
        if result.optimization is not None:
            verifiers = [r for r in manifest.runs if "cfd-verification" in r.roles]
            if len(verifiers) != 1:
                raise CrateSemanticError(
                    "an optimization crate names exactly one CFD-verification run"
                )
            verifier = verifiers[0].provenance
            assert isinstance(verifier, ProvenanceAvailable)
            if verifier.four_tuple != result.optimization.cfd_verified:
                raise CrateSemanticError(
                    "the CFD-verification run's four-tuple != optimization.cfd_verified"
                )
            for name, value in result.optimization.design_variables.items():
                if name not in v.design_space:
                    raise CrateSemanticError(f"design variable {name!r} has no applicability bound")
                lo, hi = v.design_space[name]
                if not lo <= value <= hi:
                    raise CrateSemanticError(f"design variable {name}={value} outside [{lo}, {hi}]")
    if result is None and v.validated_against_experiment:
        raise CrateSemanticError("an evidence-only crate cannot claim experiment validation")

    # Configs <-> runs; containers <-> references.
    available = [
        r.provenance for r in manifest.runs if isinstance(r.provenance, ProvenanceAvailable)
    ]
    expected = {p.four_tuple.config_hash for p in available}
    if config_hashes != expected:
        raise CrateSemanticError(
            f"config preimages {sorted(config_hashes)} != the available runs' config hashes "
            f"{sorted(expected)}"
        )
    referenced = {r.sha256 for r in manifest.references if r.role == "container" and r.sha256}
    for p in available:
        for digest in (
            p.four_tuple.container_sif_sha256,
            *(c.sha256 for c in p.four_tuple.containers),
        ):
            if digest not in referenced:
                raise CrateSemanticError(f"container digest {digest} has no container reference")

    # Required limitations, and the ADR-046 S3 sentence where it applies.
    present = {lim.id for lim in v.limitations}
    missing = required_limitations(manifest, result) - present
    if missing:
        raise CrateSemanticError(f"required limitations are missing: {sorted(missing)}")
    for lim in v.limitations:
        if lim.id == "not-flagship-domain" and FLAGSHIP_LIMITATION_SENTENCE not in lim.text:
            raise CrateSemanticError(
                f"the not-flagship-domain limitation must quote ADR-046 S3: {FLAGSHIP_LIMITATION_SENTENCE!r}"
            )

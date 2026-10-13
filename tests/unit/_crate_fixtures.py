"""Synthetic result crates for the crate tests (ADR-047). Never committed as crates.

Four payload shapes exercise every branch of format v1:

* ``steady_optimization``: a validated OptimizationResult. It has a CFD-verification run, design
  bounds, a GO verdict, the ADR-046 S3 limitation, and an embedded legacy-style source record
  that the reader replays.
* ``thesis_grade_paired``: a thesis-grade time-averaged result with a composed PAIRED delta U95
  from the committed paired fixture. That fixture carries the exact-equality validators, so it
  checks float bit-exactness end to end.
* ``independent_inf``: an IndependentDeltaU95 whose candidate statistic has the one legal
  infinity (``crosscheck_ratio``).
* ``evidence_only``: no payload and no claim, provenance unavailable, a NO-GO plus a diagnostic.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import uuid
from pathlib import Path
from typing import Any

from aero.crate import CrateSpec, EvidenceFile, build_crate
from aero.crate.model import CodeIdentity, ProvenanceAvailable, ProvenanceUnavailable, RunRecord
from aero.crate.model_base import Person, Reference
from aero.crate.validity import (
    FLAGSHIP_LIMITATION_SENTENCE,
    GateVerdict,
    Limitation,
    Unavailable,
    ValidityContext,
    Verdict,
)
from aero.provenance.four_fold import ProvenanceTuple, config_hash
from aero.vv.paired_difference import PairedDeltaUncertainty, paired_delta_uncertainty_from_samples
from aero.vv.reportable import (
    ComposedDeltaU95,
    ImprovementClaim,
    OptimizationResult,
    ReportableQuantity,
    ReportableResult,
    ValidationAnchor,
)
from aero.vv.reportable_compose import compose_improvement, compose_independent_improvement
from aero.vv.statistical_uncertainty import StatisticalUncertainty

REPO = Path(__file__).resolve().parents[2]
PAIRED_FIXTURE = REPO / "tests" / "stage_12" / "fixtures" / "paired_cycle_means.json"
DATE = dt.date(2026, 10, 12)
CREATORS = (Person(name="Louis Ernesto Schulte Moredo"),)
ADR047 = Reference(role="adr", locator="docs/adrs/ADR-047-results-must-travel-result-crates.md")
ADR046 = Reference(role="adr", locator="docs/adrs/ADR-046-stage-21-rescope-release-first.md")
SIF = "c9d7f32974c66bfbc924d407193bbf488fa165b2b35b01ee21ed9fdf9606e91c"
GIT = "0123456789abcdef0123456789abcdef01234567"


def action(n: int) -> str:
    return "#" + str(uuid.UUID(int=n, version=4))


def config(name: str, **extra: Any) -> dict[str, Any]:
    return {
        "name": name,
        "reynolds": 500000.0,
        "aoa_deg": 4.0,
        "tiny": 1e-7,
        "huge": 1.7976931348623157e308,
        **extra,
    }


def four_tuple(cfg: dict[str, Any]) -> ProvenanceTuple:
    return ProvenanceTuple(
        git_sha=GIT, dvc_input_hash="7" * 64, container_sif_sha256=SIF, config_hash=config_hash(cfg)
    )


def code(public: bool = False) -> CodeIdentity:
    return CodeIdentity(
        git_sha=GIT,
        equivalence="not-established",
        publicly_resolvable=public,
        public_refs=("refs/tags/synthetic-evidence",) if public else (),
    )


def available_run(
    run_id: str, n: int, prov: ProvenanceTuple, roles: tuple[str, ...], public: bool = False
) -> RunRecord:
    return RunRecord.model_validate(
        {
            "run_id": run_id,
            "action_id": action(n),
            "roles": roles,
            "description": f"synthetic solve {run_id}",
            "provenance": ProvenanceAvailable(four_tuple=prov, code=code(public)),
        }
    )


CONTAINER_REF = Reference(role="container", locator="containers/openfoam-esi.def", sha256=SIF)


def lim(id_: str, text: str | None = None, source: Reference = ADR047) -> Limitation:
    return Limitation.model_validate(
        {"id": id_, "kind": "statement", "text": text or f"synthetic: {id_}", "source": source}
    )


PROV_LIMITS = (lim("dvc-input-hash-sync-state"), lim("container-digest-by-lookup"))


def steady_optimization() -> CrateSpec:
    cfg = config("synthetic_opt_fine")
    prov = four_tuple(cfg)
    claim = ImprovementClaim(
        quantity="L/D",
        kind="steady",
        baseline=21.67403232277372,
        improved=46.37208685252852,
        higher_is_better=True,
        delta_uncertainty=ComposedDeltaU95(u95_numerical=2.07502863929137),
        matched_conditions=True,
    )
    result = ReportableResult(
        case_name="synthetic_opt",
        quantities=(
            ReportableQuantity(
                name="L/D", value=46.37208685252852, u95_numerical=7.033600211508836
            ),
        ),
        provenance=prov,
        optimization=OptimizationResult(
            objective="L/D",
            design_variables={
                "max_camber": 0.07142396440260919,
                "camber_position": 0.21977148504550229,
            },
            improvement=claim,
            cfd_verified=prov,
            n_candidates=74,
            held_out_verification=True,
            surrogate_predicted=True,
        ),
        validation_tag="validated",
    )
    source = EvidenceFile(
        name="synthetic_optimization.json",
        data=(result.model_dump_json(indent=2) + "\n").encode(),
        media_type="application/json",
        description="legacy-style source record (default model_dump_json)",
    )
    gate = GateVerdict(
        name="significant",
        gated=True,
        criterion="delta > k * u95_delta",
        comparator="gt",
        threshold=claim.required_margin,
        observed=claim.delta,
        passed=True,
        preregistered_in=ADR047,
    )
    validity = ValidityContext(
        claim_tier="validated",
        claim_scope="optimization",
        flagship_domain=False,
        validated_against_experiment=False,
        verdicts=(Verdict(scope="optimization-claim", overall="GO", gates=(gate,)),),
        design_space={"max_camber": (0.0, 0.08), "camber_position": (0.2, 0.6)},
        conditions={"reynolds": 500000.0, "turbulence_model": "kOmegaSST"},
        limitations=(
            *PROV_LIMITS,
            lim("input-uq-skipped"),
            lim("no-experiment-anchor"),
            lim("provenance-sha-not-public"),
            lim("not-flagship-domain", f"Airfoil only. {FLAGSHIP_LIMITATION_SENTENCE}", ADR046),
        ),
    )
    return CrateSpec(
        crate_id="stage21-synthetic-steady-opt",
        title="Synthetic steady optimization",
        description="synthetic",
        date_published=DATE,
        creators=CREATORS,
        runs=(
            available_run(
                "synthetic_opt_fine", 1, prov, ("record-of-provenance", "cfd-verification")
            ),
        ),
        validity=validity,
        result=result,
        configs=(cfg,),
        evidence=(source,),
        references=(
            CONTAINER_REF,
            Reference(
                role="source-record",
                locator="data/vv/synthetic_optimization.json",
                embedded_as="evidence/synthetic_optimization.json",
            ),
        ),
    )


PAIRED_SNAPSHOT = Path(__file__).with_name("fixtures") / "crate_paired_snapshot.json"


def _paired_from_samples() -> Any:
    data = json.loads(PAIRED_FIXTURE.read_text())
    start = data["converged_from_cycle"]
    return paired_delta_uncertainty_from_samples(
        data["baseline"]["per_cycle_mean"][start:],
        data["candidate"]["per_cycle_mean"][start:],
        period=data["period"],
        pair_start=start,
    )


def _paired() -> Any:
    """The paired estimate, loaded from a committed snapshot rather than recomputed.

    numpy's reductions (NOBM, autocorrelation) can differ in the last bit between CPUs (SIMD
    paths), so recomputing at test time made the frozen format-v1 digest machine-dependent.
    The format test pins *bytes*, not numpy. test_crate_selftest_snapshot.py keeps the
    snapshot equal to a fresh computation to within 1e-12, relative.
    """
    return PairedDeltaUncertainty.model_validate(json.loads(PAIRED_SNAPSHOT.read_text()))


def thesis_grade_paired() -> CrateSpec:
    cfg = config("synthetic_paired")
    prov = four_tuple(cfg)
    paired = _paired()
    claim = compose_improvement(
        quantity="cd",
        kind="time_averaged",
        higher_is_better=False,
        u95_delta_numerical=0.004,
        paired=paired,
    )
    result = ReportableResult(
        case_name="synthetic_paired",
        quantities=(
            ReportableQuantity(
                name="cd",
                value=paired.mean_candidate,
                kind="time_averaged",
                u95_numerical=0.004,
                u95_statistical=paired.candidate_stat.u95_statistical,
            ),
        ),
        provenance=prov,
        anchors=(
            ValidationAnchor(
                reference="lock-in",
                citation="Placzek 2009",
                tolerance=0.03,
                observed_error=0.006,
                passed=True,
            ),
        ),
        improvement=claim,
        validation_tag="thesis-grade",
    )
    validity = ValidityContext(
        claim_tier="thesis-grade",
        claim_scope="uq-reference",
        flagship_domain=False,
        validated_against_experiment=True,
        limitations=(*PROV_LIMITS, lim("input-uq-skipped"), lim("provenance-sha-not-public")),
    )
    return CrateSpec(
        crate_id="stage21-synthetic-paired",
        title="Synthetic thesis-grade paired",
        description="synthetic",
        date_published=DATE,
        creators=CREATORS,
        runs=(available_run("synthetic_paired", 2, prov, ("record-of-provenance",)),),
        validity=validity,
        result=result,
        configs=(cfg,),
        references=(CONTAINER_REF,),
    )


def _stat(mean: float, u95: float, crosscheck: float) -> StatisticalUncertainty:
    t = 3.182446305284263
    se = u95 / t
    return StatisticalUncertainty(
        n_samples=16,
        mean=mean,
        std=0.1,
        n_batches=4,
        batch_size=4,
        dof=3,
        t_quantile=t,
        se=se,
        u95_statistical=t * se,
        rel_half_width=0.01,
        autocorr_time=0.5,
        n_eff=16.0,
        crosscheck_ratio=crosscheck,
        reliable=math.isfinite(crosscheck),
    )


def independent_inf() -> CrateSpec:
    cfg = config("synthetic_independent")
    prov = four_tuple(cfg)
    base, cand = _stat(28.2007, 0.3, 1.1), _stat(49.92, 0.4, math.inf)
    claim = compose_independent_improvement(
        quantity="L/D",
        kind="time_averaged",
        higher_is_better=True,
        u95_delta_numerical=7.553810,
        baseline_stat=base,
        candidate_stat=cand,
        baseline=base.mean,
        improved=cand.mean,
    )
    result = ReportableResult(
        case_name="synthetic_independent",
        quantities=(
            ReportableQuantity(
                name="L/D",
                value=cand.mean,
                kind="time_averaged",
                u95_numerical=7.5,
                u95_statistical=0.4,
            ),
        ),
        provenance=prov,
        improvement=claim,
        validation_tag="validated",
    )
    validity = ValidityContext(
        claim_tier="validated",
        claim_scope="uq-reference",
        flagship_domain=False,
        validated_against_experiment=False,
        limitations=(
            *PROV_LIMITS,
            lim("input-uq-skipped"),
            lim("no-experiment-anchor"),
            lim("provenance-sha-not-public"),
        ),
    )
    return CrateSpec(
        crate_id="stage21-synthetic-independent",
        title="Synthetic independent delta",
        description="synthetic",
        date_published=DATE,
        creators=CREATORS,
        runs=(available_run("synthetic_independent", 3, prov, ("record-of-provenance",)),),
        validity=validity,
        result=result,
        configs=(cfg,),
        references=(CONTAINER_REF,),
    )


def evidence_only() -> CrateSpec:
    record = {
        "case": "synthetic_flapping",
        "verdict": "NO-GO",
        "gated_rel_err": 0.457,
        "band_rel": 0.25,
    }
    evidence = EvidenceFile(
        name="synthetic_nogo.json",
        data=(json.dumps(record, indent=2) + "\n").encode(),
        media_type="application/json",
        description="the hand-composed verdict record",
    )
    src = Reference(role="preregistration", locator="docs/vv/synthetic-preregistration.md")
    gates = (
        GateVerdict(
            name="mean-lift-within-band",
            gated=True,
            criterion="|mean C_L - experiment| / experiment <= 0.25",
            comparator="le",
            threshold=0.25,
            observed=0.457,
            passed=False,
            preregistered_in=src,
        ),
        GateVerdict(
            name="rotation-timing-ordering",
            gated=False,
            criterion="advanced > symmetrical > delayed mean lift (reported, never gated)",
            comparator="is-true",
            threshold=None,
            observed=True,
            passed=True,
        ),
    )
    unavailable_run = RunRecord.model_validate(
        {
            "run_id": "synthetic_flapping_symmetrical",
            "action_id": action(4),
            "roles": ("forward-validation",),
            "description": "synthetic forward run",
            "provenance": ProvenanceUnavailable(
                missing=("git_sha", "dvc_input_hash", "container_sif_sha256", "config_hash"),
                reason="the record was hand-composed and carries no four-tuple",
                code_at_tag="v0.0.14",
            ),
        }
    )
    validity = ValidityContext(
        claim_tier="none",
        claim_scope="forward-capability",
        flagship_domain=True,
        validated_against_experiment=False,
        verdicts=(Verdict(scope="forward-validation", overall="NO-GO", gates=gates),),
        limitations=(
            lim("nogo"),
            lim("diagnostic-not-gate"),
            lim("provenance-unavailable"),
            lim("no-claim"),
            Limitation(
                id="attribution-leading-hypothesis",
                kind="quote",
                text='"verdict": "NO-GO"',
                source=Reference(
                    role="source-record",
                    locator="data/vv/synthetic_nogo.json",
                    embedded_as="evidence/synthetic_nogo.json",
                ),
            ),
        ),
    )
    return CrateSpec(
        crate_id="stage21-synthetic-evidence-only",
        title="Synthetic evidence-only",
        description="synthetic",
        date_published=DATE,
        creators=CREATORS,
        runs=(unavailable_run,),
        validity=validity,
        result=None,
        evidence=(evidence,),
        unavailable=(
            Unavailable(item="four_tuple", reason="never recorded"),
            Unavailable(item="u95", reason="GCI and composition were not run"),
            Unavailable(item="case_spec", reason="no recorded config_hash"),
        ),
    )


SHAPES = {
    "steady_optimization": steady_optimization,
    "thesis_grade_paired": thesis_grade_paired,
    "independent_inf": independent_inf,
    "evidence_only": evidence_only,
}


def built(shape: str) -> dict[str, bytes]:
    return build_crate(SHAPES[shape]())

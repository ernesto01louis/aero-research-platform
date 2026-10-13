#!/usr/bin/env python3
"""Export the five v0.1.0 result crates from the committed records (Stage 21, ADR-047 D7).

    python scripts/stage21_export_crates.py write [--crate ID] [--replace]
    python scripts/stage21_export_crates.py check [--out DIR]

``write`` is ONE-SHOT. It builds each crate from an explicit record-of-record registry and never
globs. It reconstructs every run's as-hashed config with the ERA RECIPE of the code that ran it,
and asserts the reconstruction reproduces the recorded ``config_hash`` before anything is written.
CaseSpec has gained fields since the runs: ``section`` at Stage 20, ``first_cell_*`` at Stage 16,
and the Stage-16 graded default. HEAD's models therefore no longer hash to the recorded values;
the recipes below are the record of exactly how each era's payload looked.

``check`` is what CI and the tests run. It NEVER re-runs a recipe, because a future CaseSpec field
must not turn CI red. Instead it:
- verifies every committed crate;
- requires every embedded evidence member to equal its repository file;
- requires the Stage-17 corpus md5 to equal its DVC pointer;
- checks each run's code identity against git;
- checks the digest table in ``crates/README.md``.

Crates go to ``crates/<crate_id>/``, never under ``data/vv/`` (the writer refuses that path).
The content licence is CC-BY-4.0 (operator decision D3, 2026-10-11).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from aero.crate import CrateSpec, EvidenceFile, build_crate, verify_crate, write_crate  # noqa: E402
from aero.crate.model import (  # noqa: E402
    CodeIdentity,
    ProvenanceAvailable,
    ProvenanceUnavailable,
    RunRecord,
)
from aero.crate.model_base import Person, Reference  # noqa: E402
from aero.crate.payload import load_reportable  # noqa: E402
from aero.crate.validity import (  # noqa: E402
    FLAGSHIP_LIMITATION_SENTENCE,
    GateVerdict,
    Limitation,
    Unavailable,
    ValidityContext,
    Verdict,
)
from aero.provenance.four_fold import ProvenanceTuple, config_hash  # noqa: E402
from aero.vv.reportable import ReportableResult  # noqa: E402

CRATES = REPO / "crates"
DATE = dt.date(2026, 10, 12)
CREATORS = (Person(name="Louis Ernesto Schulte Moredo"),)
SIF_NAME = "openfoam-esi.sif"
CODE_PATHS = ("aero", "scripts", "conf", "containers", "pyproject.toml", "uv.lock")

# The commit on main at which the cited repository texts (handoffs, ADRs, CHANGELOG) were read.
# It is an ancestor of every later main, so the references stay resolvable.
DOCS_COMMIT = "83baa43225cd9a5f9684a0481b8502b6004fa49c"

EVIDENCE_TAGS = {
    "a5c759a252cf": "stage-12-evidence-2026-07-05",
    "3dc4d308e105": "stage-15-evidence-2026-07-12",
    "2e7106ac": "stage-16-evidence-2026-07-15",
    "6b904e83": "stage-16-evidence-2026-07-15",
    "30595a39371d": "stage-17-evidence-2026-07-24",
}


# --------------------------------------------------------------------------------------------
# git helpers (export time only)
# --------------------------------------------------------------------------------------------


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()


def _tag_commit(tag: str) -> str:
    return _git("rev-list", "-n1", tag)


def code_identity(sha: str, stage_tag: str) -> CodeIdentity:
    """git_sha's relation to the stage tag and the public refs that hold it, measured now."""
    tag_commit = _tag_commit(stage_tag)
    differing = tuple(
        p for p in _git("diff", "--name-only", sha, tag_commit, "--", *CODE_PATHS).splitlines() if p
    )
    if sha == tag_commit:
        equivalence = "is-tag-commit"
    elif differing:
        equivalence = "code-trees-differ"
    else:
        equivalence = "code-trees-identical"
    tag = next((t for prefix, t in EVIDENCE_TAGS.items() if sha.startswith(prefix)), None)
    public = ()
    if tag is not None:
        remote = _git("ls-remote", "--tags", "origin", f"refs/tags/{tag}")
        contained = (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", sha, tag], cwd=REPO, check=False
            ).returncode
            == 0
        )
        if remote and contained:
            public = (f"refs/tags/{tag}",)
    return CodeIdentity(
        git_sha=sha,
        equivalent_tag=stage_tag,
        equivalent_tag_commit=tag_commit,
        equivalence=equivalence,
        differing_paths=differing,
        publicly_resolvable=bool(public),
        public_refs=public,
    )


def action_id(crate_id: str, run_id: str) -> str:
    """A fixed, valid UUIDv4 per (crate, run): re-export is idempotent."""
    digest = hashlib.sha256(f"{crate_id}/{run_id}".encode()).digest()[:16]
    return "#" + str(uuid.UUID(bytes=digest, version=4))


def _record(name: str) -> bytes:
    return (REPO / "data" / "vv" / f"{name}.json").read_bytes()


def _json(name: str) -> Any:
    return json.loads(_record(name))


def _evidence(
    rel: str, description: str, media: str = "application/json", name: str | None = None
) -> EvidenceFile:
    data = (REPO / rel).read_bytes()
    return EvidenceFile(
        name=name or Path(rel).name, data=data, media_type=media, description=description
    )


def _lines(rel: str, first: int, last: int) -> str:
    """Lines first..last (1-based, inclusive) of a repo file, verbatim, for a quoted limitation."""
    return "\n".join((REPO / rel).read_text(encoding="utf-8").splitlines()[first - 1 : last])


def _ref(
    role: str, locator: str, lines: str | None = None, embedded_as: str | None = None
) -> Reference:
    commit = (
        DOCS_COMMIT if embedded_as is None and not locator.startswith(("http", "doi:")) else None
    )
    sha = None
    if embedded_as is not None:
        sha = hashlib.sha256((REPO / locator).read_bytes()).hexdigest()
    return Reference.model_validate(
        {
            "role": role,
            "locator": locator,
            "commit": commit,
            "lines": lines,
            "sha256": sha,
            "embedded_as": embedded_as,
        }
    )


def _container_ref() -> Reference:
    for line in (REPO / "containers" / "SHA256SUMS").read_text().splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == SIF_NAME:
            return Reference(role="container", locator=SIF_NAME, sha256=parts[0])
    raise SystemExit(f"{SIF_NAME} not in containers/SHA256SUMS")


def _lim(id_: str, text: str, source: Reference, kind: str = "statement") -> Limitation:
    return Limitation.model_validate({"id": id_, "kind": kind, "text": text, "source": source})


def _available(
    crate_id: str,
    run_id: str,
    roles: tuple[str, ...],
    tup: dict[str, Any],
    tag: str,
    description: str,
) -> RunRecord:
    four = ProvenanceTuple.model_validate(tup)
    return RunRecord.model_validate(
        {
            "run_id": run_id,
            "action_id": action_id(crate_id, run_id),
            "roles": roles,
            "description": description,
            "provenance": ProvenanceAvailable(
                four_tuple=four, code=code_identity(four.git_sha, tag)
            ),
        }
    )


def _assert_hash(cfg: dict[str, Any], want: str, what: str) -> dict[str, Any]:
    got = config_hash(cfg)
    if got != want:
        raise SystemExit(f"ERA RECIPE MISMATCH for {what}: {got} != recorded {want}")
    return cfg


# Shared limitation sources.
ADR046 = _ref("adr", "docs/adrs/ADR-046-stage-21-rescope-release-first.md", "96-99")
DVC_HASH = _ref("code", "aero/provenance/four_fold.py", "229-247")
SIF_LOOKUP = _ref("code", "aero/provenance/four_fold.py", "250-264")
ADR015 = _ref("adr", "docs/adrs/ADR-015-small-signal-and-data-origin-invariants.md")
ADR032_CERT = _ref(
    "adr", "docs/adrs/ADR-032-surrogate-accelerated-loop-and-speedup-protocol.md", "71-72"
)
ADR032_S6 = _ref(
    "adr", "docs/adrs/ADR-032-surrogate-accelerated-loop-and-speedup-protocol.md", "100-101"
)


def _common_limitations(source_for_anchor: Reference | None) -> list[Limitation]:
    out = [
        _lim(
            "dvc-input-hash-sync-state",
            "dvc_input_hash is the sha256 of the DVC remote sync state (`dvc status -c`), not a "
            "content address of the inputs: one constant value appears across all 74 occurrences "
            "in data/vv. It shows the inputs were in sync with the remote at run time; it does "
            "not identify them.",
            DVC_HASH,
        ),
        _lim(
            "container-digest-by-lookup",
            "container_sif_sha256 is looked up by SIF basename in containers/SHA256SUMS at run "
            "time; the SIF that actually ran was not re-hashed (review item P1c).",
            SIF_LOOKUP,
        ),
        _lim(
            "input-uq-skipped",
            "No input (parametric) uncertainty quantification was performed: u95_input is 0 "
            "with basis 'skipped', so U95 here is numerical (+ statistical where stated) only.",
            _ref("code", "aero/vv/reportable.py", "144-156"),
        ),
    ]
    if source_for_anchor is not None:
        out.append(
            _lim(
                "no-experiment-anchor",
                "The airfoil objective's forward model (k-omega SST, wall functions, Re 5e5) has no "
                "experiment anchor: anchors = [] in the record. Improvements are matched-condition "
                "CFD deltas, not validated absolute values.",
                source_for_anchor,
            )
        )
    return out


def _flagship_limitation() -> Limitation:
    return _lim(
        "not-flagship-domain",
        "This optimization is on the AIRFOIL case. The optimizer has never been run on a "
        f"flapping-wing case. {FLAGSHIP_LIMITATION_SENTENCE}",
        ADR046,
    )


AIRFOIL_SPACE = {"max_camber": (0.0, 0.08), "camber_position": (0.2, 0.6)}
AIRFOIL_CONDITIONS: dict[str, float | str] = {
    "reynolds": 500000.0,
    "aoa_deg": 4.0,
    "model": "RANS k-omega SST, wall functions, NACA-4 camber line",
}


# --------------------------------------------------------------------------------------------
# Stage 12 -- the only thesis-grade record (the U95 reference)
# --------------------------------------------------------------------------------------------


def stage12() -> CrateSpec:
    from aero.vv.unsteady import UNSTEADY_CASES

    crate_id = "stage12-oscillating-cylinder-lockin"
    raw = _record("stage12_reportable_oscillating_cylinder_lockin")
    result = load_reportable(raw, mode="legacy")
    tup = result.provenance
    cfg = _assert_hash(
        UNSTEADY_CASES["oscillating_cylinder_lockin"].case_spec().model_dump(mode="json"),
        tup.config_hash,
        "stage12 lock-in",
    )
    src = _ref(
        "source-record",
        "data/vv/stage12_reportable_oscillating_cylinder_lockin.json",
        embedded_as="evidence/stage12_reportable_oscillating_cylinder_lockin.json",
    )
    anchor = result.anchors[0]
    gates = (
        GateVerdict(
            name="lock-in-anchor",
            gated=True,
            criterion=f"{anchor.reference}: observed error <= tolerance",
            comparator="le",
            threshold=anchor.tolerance,
            observed=anchor.observed_error,
            passed=anchor.passed,
            # The 3 % tolerance as fixed in code; unchanged between the run commit and DOCS_COMMIT.
            preregistered_in=_ref("code", "aero/vv/unsteady/oscillating_cylinder.py", "87-90"),
        ),
    )
    handoff = _ref("handoff", "docs/handoffs/STAGE-12-vv-uq-core-DONE-2026-07-05.md")
    limitations = [
        *_common_limitations(None),
        _lim(
            "uq-reference-outside-release-narrative",
            "A U95-machinery reference, not part of the optimizer demonstration: the only "
            "thesis-grade record committed, carrying both a numerical (GCI) and a statistical "
            "(batch-means) U95 term and a passing experiment anchor.",
            handoff,
        ),
    ]
    return CrateSpec(
        crate_id=crate_id,
        title="Stage 12: oscillating-cylinder lock-in, thesis-grade U95 reference",
        description="Time-averaged drag coefficient of a cylinder in forced oscillation (wake "
        "lock-in), with GCI + batch-means U95 and a passing lock-in anchor. thesis-grade.",
        date_published=DATE,
        creators=CREATORS,
        runs=(
            _available(
                crate_id,
                "oscillating_cylinder_lockin",
                ("record-of-provenance",),
                tup.model_dump(mode="json"),
                "v0.0.12",
                "the lock-in solve the record cites",
            ),
        ),
        validity=ValidityContext(
            claim_tier="thesis-grade",
            claim_scope="uq-reference",
            flagship_domain=False,
            validated_against_experiment=True,
            verdicts=(Verdict(scope="thesis-grade-gate", overall="GO", gates=gates),),
            limitations=tuple(limitations),
        ),
        result=result,
        configs=(cfg,),
        evidence=(
            _evidence(
                "data/vv/stage12_reportable_oscillating_cylinder_lockin.json",
                "the committed record",
            ),
            _evidence("data/vv/stage12_cylinder_gci.json", "the GCI study behind u95_numerical"),
        ),
        references=(src, _container_ref(), handoff),
    )


# --------------------------------------------------------------------------------------------
# Stage 14 -- the flagship forward capability: evidence only, no claim
# --------------------------------------------------------------------------------------------


def stage14() -> CrateSpec:
    crate_id = "stage14-rigid-flapping-wbd2004"
    rec = _json("stage14_flapping_nogo")
    per = {p["timing"]: p for p in rec["per_timing"]}
    prereg = _ref(
        "preregistration",
        "docs/vv/stage14-preregistration.md",
        embedded_as="evidence/stage14-preregistration.md",
    )
    prereg_diag = prereg.model_copy(update={"lines": "51-56"})
    handoff = _ref(
        "handoff", "docs/handoffs/STAGE-14-rigid-flapping-wing-DONE-2026-07-10.md", "29-33"
    )
    handoff_conf = _ref(
        "handoff", "docs/handoffs/STAGE-14-rigid-flapping-wing-DONE-2026-07-10.md", "153-154"
    )
    # "dataset", not "source-record": there is no ReportableResult to replay it against.
    record_ref = _ref(
        "dataset",
        "data/vv/stage14_flapping_nogo.json",
        embedded_as="evidence/stage14_flapping_nogo.json",
    )
    runs = tuple(
        RunRecord.model_validate(
            {
                "run_id": f"flapping_wing_wbd2004_{timing}",
                "action_id": action_id(crate_id, timing),
                "roles": ("forward-validation",),
                "description": f"{timing} rotation timing, {per[timing]['ncyc']} stroke cycles",
                "provenance": ProvenanceUnavailable(
                    missing=("git_sha", "dvc_input_hash", "container_sif_sha256", "config_hash"),
                    reason="the committed verdict record was hand-composed and carries no "
                    "four-tuple, no run id and no config hash; the Stage-14 GCI and thesis-grade "
                    "composition were not run",
                    code_at_tag="v0.0.14",
                ),
            }
        )
        for timing in ("symmetrical", "advanced", "delayed")
    )
    gates = (
        GateVerdict(
            name="symmetrical-mean-lift-within-band",
            gated=True,
            criterion="symmetrical stroke-averaged mean C_L within +-25 % of the WBD (2004) "
            "experiment (0.86); band pre-registered, NOT relaxed",
            comparator="le",
            threshold=float(rec["band_rel"]),
            observed=float(rec["gated_rel_err"]),
            passed=False,
            preregistered_in=prereg,
        ),
        GateVerdict(
            name="rotation-timing-ordering",
            gated=False,
            criterion="advanced > symmetrical > delayed mean lift (reported, NEVER gated)",
            comparator="is-true",
            threshold=None,
            observed=bool(rec["ordering_correct"]),
            passed=bool(rec["ordering_correct"]),
        ),
        GateVerdict(
            name="advanced-mean-lift-rel-err",
            gated=False,
            criterion="advanced mean C_L vs experiment 0.93 within 25 % (reported, never gated)",
            comparator="le",
            threshold=0.25,
            observed=float(per["advanced"]["rel_err_vs_exp"]),
            passed=False,
        ),
        GateVerdict(
            name="delayed-mean-lift-rel-err",
            gated=False,
            criterion="delayed mean C_L vs experiment 0.38 within 25 % (reported, never gated; "
            "a documented 2-D limitation)",
            comparator="le",
            threshold=0.25,
            observed=float(per["delayed"]["rel_err_vs_exp"]),
            passed=False,
        ),
    )
    limitations = (
        _lim(
            "no-claim",
            "Evidence only, no claim: no four-tuple, U95 or config hash was recorded for these "
            "runs, so they cannot carry a validation tier. The optimizer has never been run on a "
            f"flapping-wing case. {FLAGSHIP_LIMITATION_SENTENCE}",
            record_ref,
        ),
        _lim(
            "nogo",
            "NO-GO on the gated quantity: the symmetrical stroke-averaged mean lift misses the WBD "
            "(2004) experiment by 45.7 % against a pre-registered +-25 % band; the band was not "
            "relaxed.",
            handoff,
        ),
        _lim(
            "diagnostic-not-gate",
            _lines("docs/vv/stage14-preregistration.md", 51, 56),
            prereg_diag,
            kind="quote",
        ),
        _lim(
            "provenance-unavailable",
            "No run of this crate has a recorded four-tuple (git SHA, DVC input hash, container "
            "digest, config hash). The code is identified only as the v0.0.14 tag.",
            record_ref,
        ),
        _lim(
            "attribution-leading-hypothesis",
            "The record's root_cause names overset wake-capture dissipation. The Stage-14 handoff "
            "states that attribution as the leading hypothesis: it could not be isolated against "
            "a body-fitted run at this amplitude.",
            handoff_conf,
        ),
    )
    return CrateSpec(
        crate_id=crate_id,
        title="Stage 14: rigid flapping wing vs Wang-Birch-Dickinson 2004 (evidence only)",
        description="The flagship flapping-wing forward capability. The rotation-timing "
        "ordering is reproduced as a pre-registered, NON-gated diagnostic; the gated mean lift is "
        "a documented NO-GO. Evidence only: provenance was never recorded, so no claim.",
        date_published=DATE,
        creators=CREATORS,
        runs=runs,
        validity=ValidityContext(
            claim_tier="none",
            claim_scope="forward-capability",
            flagship_domain=True,
            validated_against_experiment=False,
            verdicts=(Verdict(scope="forward-validation", overall="NO-GO", gates=gates),),
            conditions={
                "reynolds": 75.0,
                "geometry": "2-D ellipse, prescribed translation + pitch",
            },
            limitations=limitations,
        ),
        result=None,
        evidence=(
            _evidence("data/vv/stage14_flapping_nogo.json", "the committed NO-GO verdict record"),
            _evidence(
                "docs/vv/stage14-preregistration.md",
                "the gate pre-registration",
                media="text/markdown",
            ),
        ),
        references=(
            record_ref,
            prereg,
            handoff,
            Reference(role="reference-data", locator="https://doi.org/10.1242/jeb.00739"),
            Reference(
                role="reference-data",
                locator="data/references/flapping/wbd2004_2d_ellipse/mean_coefficients.csv",
                commit=_tag_commit("v0.0.14"),
                sha256=hashlib.sha256(
                    (
                        REPO / "data/references/flapping/wbd2004_2d_ellipse/mean_coefficients.csv"
                    ).read_bytes()
                ).hexdigest(),
            ),
        ),
        unavailable=(
            Unavailable(item="four_tuple", reason="never recorded for the Stage-14 campaign runs"),
            Unavailable(item="u95", reason="GCI and thesis-grade composition were not run"),
            Unavailable(
                item="case_spec", reason="no config hash was recorded to verify one against"
            ),
            Unavailable(item="raw_series", reason="force histories live on cluster NFS only"),
        ),
    )


# --------------------------------------------------------------------------------------------
# Stage 15 / 16 / 17 -- the airfoil optimizer
# --------------------------------------------------------------------------------------------


def _s15_cfg(m: float, p: float, name: str, mult: float) -> dict[str, Any]:
    from aero.optimize.turbulent_airfoil import ShapedTurbulentAirfoil

    case = ShapedTurbulentAirfoil(
        name=name, aoa_deg=4.0, reynolds=5e5, max_camber=m, camber_position=p, end_time=3000
    )
    if mult != 1.0:
        case = case.refined(mult, graded=False)  # the Stage-15 count-only family
    d = case.case_spec().model_dump(mode="json")
    for key in ("section", "first_cell_front", "first_cell_wake"):  # added at Stages 20 / 16
        d.pop(key, None)
    return d


def stage15() -> CrateSpec:
    crate_id = "stage15-airfoil-optimization"
    result = load_reportable(_record("stage15_optimization"), mode="legacy")
    conv = _json("stage15_grid_convergence")
    m_opt = conv["design_optimum"]["max_camber"]
    p_opt = conv["design_optimum"]["camber_position"]
    runs, configs = [], []
    for row in conv["solves"]:
        name = f"gm_{row['design']}_{row['grid']}"
        m = m_opt if row["design"] == "optimum" else 0.0
        configs.append(
            _assert_hash(
                _s15_cfg(m, p_opt, name, row["refine_mult"]), row["provenance"]["config_hash"], name
            )
        )
        runs.append(
            _available(
                crate_id,
                name,
                ("grid-family",),
                row["provenance"],
                "v0.0.15",
                f"{row['design']} design, {row['grid']} grid (x{row['refine_mult']:.4g})",
            )
        )
    configs.append(
        _assert_hash(
            _s15_cfg(m_opt, p_opt, "gm_optimum_fine", 1.0),
            result.provenance.config_hash,
            "gm_optimum_fine (held out)",
        )
    )
    runs.insert(
        0,
        _available(
            crate_id,
            "gm_optimum_fine-heldout",
            ("record-of-provenance",),
            result.provenance.model_dump(mode="json"),
            "v0.0.15",
            "held-out re-verification of the optimum on the finest grid",
        ),
    )
    src = _ref(
        "source-record",
        "data/vv/stage15_optimization.json",
        embedded_as="evidence/stage15_optimization.json",
    )
    conv_ref = _ref(
        "dataset",
        "data/vv/stage15_grid_convergence.json",
        embedded_as="evidence/stage15_grid_convergence.json",
    )
    inv10 = ADR015
    gates = (
        GateVerdict(
            name="delta-exceeds-k-u95",
            gated=True,
            criterion="matched delta > k * U95_delta with k = 2 (Invariant 10)",
            comparator="gt",
            threshold=conv["required_margin"],
            observed=conv["delta_fine"],
            passed=False,
            preregistered_in=inv10,
        ),
        GateVerdict(
            name="delta-exceeds-own-u95",
            gated=False,
            criterion="matched delta > 1 * U95_delta (reported)",
            comparator="gt",
            threshold=conv["u95_delta_numerical"],
            observed=conv["delta_fine"],
            passed=conv["delta_fine"] > conv["u95_delta_numerical"],
        ),
        GateVerdict(
            name="observed-order-in-asymptotic-range",
            gated=False,
            criterion="observed order of the delta within [0.5, 2.0] (reported; not gated at Stage 15)",
            comparator="within",
            threshold=(0.5, 2.0),
            observed=conv["observed_order_delta"],
            passed=0.5 <= conv["observed_order_delta"] <= 2.0,
        ),
        GateVerdict(
            name="all-solves-converged",
            gated=False,
            criterion="every solve of the family converged (reported)",
            comparator="is-true",
            threshold=None,
            observed=bool(conv["all_converged"]),
            passed=bool(conv["all_converged"]),
        ),
    )
    changelog = _ref("handoff", "CHANGELOG.md", "278-282")
    limitations = [
        *_common_limitations(src),
        _flagship_limitation(),
        _lim(
            "nogo",
            "NO-GO: the optimum's matched delta 24.66 did NOT exceed even its own U95 of 25.37 "
            "(the gated bar is 2 x U95 = 50.75). The family is not grid-converged (observed order "
            "-1.10). The +113.8 % baseline-to-optimum change is NOT an improvement claim.",
            src,
        ),
        _lim(
            "retracted-claim",
            "An earlier draft claimed a '+47 % thesis-grade CFD-verified improvement'. It was "
            "withdrawn after an adversarial audit and a 3-grid observed-order V&V refuted it.",
            changelog,
        ),
        _lim(
            "diagnostic-not-gate",
            "Only 'delta-exceeds-k-u95' decided the Stage-15 verdict. The other gates are reported "
            "diagnostics.",
            src,
        ),
    ]
    return CrateSpec(
        crate_id=crate_id,
        title="Stage 15: CFD-in-the-loop airfoil optimization (NO-GO, delta inside its U95)",
        description="Direct-CFD Bayesian optimization of a NACA-4 camber line for L/D at Re 5e5, "
        "AoA 4 deg, re-verified on a 3-grid family. NO-GO: the matched delta is not significant. "
        "validated tier, airfoil only.",
        date_published=DATE,
        creators=CREATORS,
        runs=tuple(runs),
        validity=ValidityContext(
            claim_tier="validated",
            claim_scope="optimization",
            flagship_domain=False,
            validated_against_experiment=False,
            verdicts=(Verdict(scope="optimization-claim", overall="NO-GO", gates=gates),),
            design_space=AIRFOIL_SPACE,
            conditions=AIRFOIL_CONDITIONS,
            limitations=tuple(limitations),
        ),
        result=result,
        configs=tuple(configs),
        evidence=(
            _evidence("data/vv/stage15_optimization.json", "the committed record"),
            _evidence("data/vv/stage15_grid_convergence.json", "the 3-grid family and its GCI"),
        ),
        references=(
            src,
            conv_ref,
            _container_ref(),
            changelog,
            _ref(
                "handoff",
                "docs/handoffs/STAGE-15-cfd-in-the-loop-airfoil-optimization-DONE-2026-07-11.md",
            ),
        ),
    )


def _s16_cfg(
    m: float, p: float, name: str, mult: float, conv: dict[str, Any], init: bool
) -> dict[str, Any]:
    from aero.adapters.openfoam.transient_airfoil import TransientAirfoilSpec
    from aero.optimize.turbulent_airfoil import ShapedTurbulentAirfoil

    steady = ShapedTurbulentAirfoil(
        name=name, aoa_deg=4.0, reynolds=5e5, max_camber=m, camber_position=p
    )
    base = steady.refined(mult).case_spec() if mult != 1.0 else steady.case_spec()
    spec = TransientAirfoilSpec(
        base=base, end_time_convective=conv["end_time_convective"], max_courant=conv["max_courant"]
    )
    d = spec.model_dump(mode="json")
    d["base"].pop("section", None)  # added at Stage 20
    if init:
        d = {**d, "initialization": "steady-RANS fields (time-accurate relaxation)"}
    return d


def stage16() -> CrateSpec:
    crate_id = "stage16-airfoil-grid-certification"
    result = load_reportable(_record("stage16_relaxed_optimization"), mode="legacy")
    conv = _json("stage16_relaxed_convergence")
    m_opt = conv["design_optimum"]["max_camber"]
    p_opt = conv["design_optimum"]["camber_position"]
    runs, configs = [], []
    for row in conv["solves"]:
        as_run = re.sub(r"-\d{8}-\d{6}$", "", row["run_id"])  # the name each solve RAN under
        m = m_opt if row["design"] == "optimum" else 0.0
        configs.append(
            _assert_hash(
                _s16_cfg(m, p_opt, as_run, row["refine_mult"], conv, True),
                row["provenance"]["config_hash"],
                row["run_id"],
            )
        )
        runs.append(
            _available(
                crate_id,
                row["run_id"],
                ("grid-family",),
                row["provenance"],
                "v0.0.16",
                f"{row['design']} design, {row['grid']} grid (x{row['refine_mult']:.4g}), "
                "time-accurate relaxation",
            )
        )
    configs.append(
        _assert_hash(
            _s16_cfg(m_opt, p_opt, "g16r_optimum_fine", conv["finest_mult"], conv, False),
            result.provenance.config_hash,
            "g16r_optimum_fine (spec identity)",
        )
    )
    runs.insert(
        0,
        _available(
            crate_id,
            "g16r_optimum_fine-spec-identity",
            ("record-of-provenance",),
            result.provenance.model_dump(mode="json"),
            "v0.0.16",
            "the held-out optimum's spec identity the record cites",
        ),
    )
    src = _ref(
        "source-record",
        "data/vv/stage16_relaxed_optimization.json",
        embedded_as="evidence/stage16_relaxed_optimization.json",
    )
    conv_ref = _ref(
        "dataset",
        "data/vv/stage16_relaxed_convergence.json",
        embedded_as="evidence/stage16_relaxed_convergence.json",
    )
    adr030 = _ref(
        "adr", "docs/adrs/ADR-030-relaxation-certification-and-spurious-attractor.md", "75-81"
    )
    g = conv["gates"]
    gates = (
        GateVerdict(
            name="significant",
            gated=True,
            criterion="matched delta > 2 * U95_delta (fallback GCI, Fs=3, p=1)",
            comparator="gt",
            threshold=conv["required_margin"],
            observed=conv["delta_fine"],
            passed=bool(g["significant"]),
            preregistered_in=adr030,
        ),
        GateVerdict(
            name="all-converged",
            gated=True,
            criterion="every claim-grid solve converged",
            comparator="is-true",
            threshold=None,
            observed=bool(g["all_converged"]),
            passed=bool(g["all_converged"]),
            preregistered_in=adr030,
        ),
        GateVerdict(
            name="delta-monotone",
            gated=True,
            criterion="the delta is monotone across the family",
            comparator="is-true",
            threshold=None,
            observed=bool(g["delta_monotone"]),
            passed=bool(g["delta_monotone"]),
            preregistered_in=adr030,
        ),
        GateVerdict(
            name="order-in-asymptotic-range",
            gated=True,
            criterion="observed order of the delta within [0.5, 2.0] (floor pre-registered "
            "before any campaign ran; not adjusted)",
            comparator="within",
            threshold=(0.5, 2.0),
            observed=conv["observed_order_delta"],
            passed=bool(g["order_in_asymptotic_range"]),
            preregistered_in=adr030,
        ),
    )
    limitations = [
        *_common_limitations(src),
        _flagship_limitation(),
        _lim(
            "nogo",
            "Honest NO-GO by exactly one pre-registered gate: observed order 0.465 vs the 0.5 floor. "
            "At that measured order the same GCI construction gives 2 x U95 ~ 37.7, which the delta "
            "21.72 would not clear. The result ships at validated tier.",
            adr030,
        ),
        _lim(
            "record-provenance-is-spec-identity",
            "The record's four-tuple is the held-out optimum's SPEC identity (config without the "
            "'initialization' key). The grid-family solves were hashed with that key, so they carry "
            "different config hashes; both preimages are in this crate.",
            src,
        ),
        _lim(
            "superseded-campaign",
            "data/vv/stage16_optimization.json and stage16_grid_convergence.json record the "
            "SUPERSEDED steady graded campaign (NO-GO on all four hard gates). This crate carries "
            "the record of record, the time-accurate relaxation.",
            _ref(
                "handoff",
                "docs/handoffs/STAGE-16-grid-converged-certification-DONE-2026-07-15.md",
                "39-42",
            ),
        ),
    ]
    return CrateSpec(
        crate_id=crate_id,
        title="Stage 16: grid-converged certification of the airfoil optimum (NO-GO by one gate)",
        description="3-grid observed-order GCI on the matched L/D delta, URANS-stabilized values. "
        "NO-GO by one pre-registered gate (observed order 0.465 vs 0.5). validated tier, airfoil only.",
        date_published=DATE,
        creators=CREATORS,
        runs=tuple(runs),
        validity=ValidityContext(
            claim_tier="validated",
            claim_scope="optimization",
            flagship_domain=False,
            validated_against_experiment=False,
            verdicts=(Verdict(scope="grid-certification", overall="NO-GO", gates=gates),),
            design_space=AIRFOIL_SPACE,
            conditions={**AIRFOIL_CONDITIONS, "max_courant": float(conv["max_courant"])},
            limitations=tuple(limitations),
        ),
        result=result,
        configs=tuple(configs),
        evidence=(
            _evidence(
                "data/vv/stage16_relaxed_optimization.json", "the committed record of record"
            ),
            _evidence(
                "data/vv/stage16_relaxed_convergence.json", "the 4-level family, gates and GCI"
            ),
        ),
        references=(
            src,
            conv_ref,
            _container_ref(),
            adr030,
            _ref("superseded-record", "data/vv/stage16_optimization.json"),
        ),
    )


def stage17() -> CrateSpec:
    from aero.optimize.turbulent_airfoil import ShapedTurbulentAirfoil

    crate_id = "stage17-surrogate-accelerated-optimization"
    result: ReportableResult = load_reportable(_record("stage17_optimization"), mode="legacy")
    opt = result.optimization
    assert opt is not None
    dv = opt.design_variables
    cfg = (
        ShapedTurbulentAirfoil(
            name="s17v_opt_fine",
            aoa_deg=4.0,
            reynolds=5e5,
            max_camber=dv["max_camber"],
            camber_position=dv["camber_position"],
            end_time=3000,
        )
        .case_spec()
        .model_dump(mode="json")
    )
    cfg.pop("section", None)  # added at Stage 20
    _assert_hash(cfg, result.provenance.config_hash, "s17v_opt_fine")
    speed = _json("stage17_speedup")
    cert = _json("stage17_surrogate_cert")
    explore = _json("stage17_arm_surrogate_explore")
    proposer = explore["accelerated"]["records"][1]["certificate"]
    corpus_rel = "data/datasets/stage17_naca4_ld/corpus.json"
    dvc_md5 = re.search(r"md5: ([0-9a-f]{32})", (REPO / f"{corpus_rel}.dvc").read_text()).group(1)  # type: ignore[union-attr]
    if hashlib.md5((REPO / corpus_rel).read_bytes(), usedforsecurity=False).hexdigest() != dvc_md5:
        raise SystemExit("the local corpus.json does not match its DVC pointer: run `dvc pull`")
    src = _ref(
        "source-record",
        "data/vv/stage17_optimization.json",
        embedded_as="evidence/stage17_optimization.json",
    )
    speed_ref = _ref(
        "dataset", "data/vv/stage17_speedup.json", embedded_as="evidence/stage17_speedup.json"
    )
    cert_ref = _ref(
        "dataset",
        "data/vv/stage17_surrogate_cert.json",
        embedded_as="evidence/stage17_surrogate_cert.json",
    )
    explore_ref = _ref(
        "dataset",
        "data/vv/stage17_arm_surrogate_explore.json",
        embedded_as="evidence/stage17_arm_surrogate_explore.json",
    )
    inv10 = ADR015
    claim = opt.improvement
    corpus = json.loads((REPO / corpus_rel).read_bytes())
    corpus_best = max(row["ld"] for row in corpus["rows"] if not row["failed"])
    q_u95 = result.quantities[0].u95_numerical
    v = speed["verification"]
    gates_claim = (
        GateVerdict(
            name="delta-exceeds-k-u95",
            gated=True,
            criterion="CFD-verified delta vs the baseline > k * U95_delta, k = 2 (2-grid GCI)",
            comparator="gt",
            threshold=claim.required_margin,
            observed=claim.delta,
            passed=True,
            preregistered_in=inv10,
        ),
        GateVerdict(
            name="margin-over-corpus-best-exceeds-u95",
            gated=False,
            criterion=f"reported L/D minus the corpus best ({corpus_best!r}, the best of the 42 "
            "corpus solves) > the quantity's U95 (reported)",
            comparator="gt",
            threshold=q_u95,
            observed=result.quantities[0].value - corpus_best,
            passed=False,
        ),
        GateVerdict(
            name="held-out-is-same-grid-re-solve",
            gated=False,
            criterion="the held-out verification is a deterministic same-grid re-solve that "
            "reproduces the loop's value bit for bit (reported)",
            comparator="is-true",
            threshold=None,
            observed=bool(v["V1_held_out_ld"] == speed["reported_optimum"]["loop_best_ld"]),
            passed=bool(v["V1_held_out_ld"] == speed["reported_optimum"]["loop_best_ld"]),
        ),
        GateVerdict(
            name="proposer-certificate-p95-within-bar",
            gated=False,
            criterion="the in-loop ensemble that proposed the optimum, judged by C2: held-out "
            "|L/D error| p95 <= 2.5 (reported; it was smoke tier by design)",
            comparator="le",
            threshold=2.5,
            observed=float(proposer["held_out_metrics"]["ld_mae"]["p95"]),
            passed=False,
        ),
        GateVerdict(
            name="proposer-certificate-coverage-in-band",
            gated=False,
            criterion="the in-loop ensemble that proposed the optimum, judged by C1: empirical "
            "+-2 std coverage in [0.85, 1.0] (reported; smoke tier by design)",
            comparator="within",
            threshold=(0.85, 1.0),
            observed=float(proposer["uncertainty_calibration"]["empirical_coverage"]),
            passed=False,
        ),
    )
    gates_cert = (
        GateVerdict(
            name="c1-coverage-in-band",
            gated=True,
            criterion="C1 empirical +-2 std coverage in [0.85, 1.0] (seeded 25 % held-out split)",
            comparator="within",
            threshold=tuple(cert["gates"]["C1_coverage_band"]),  # type: ignore[arg-type]
            observed=float(cert["gates"]["C1_empirical_coverage"]),
            passed=True,
            preregistered_in=ADR032_CERT,
        ),
        GateVerdict(
            name="c2-p95-within-bar",
            gated=True,
            criterion="C2 held-out |L/D error| p95 <= 2.5",
            comparator="le",
            threshold=float(cert["gates"]["C2_p95_bar"]),
            observed=float(cert["gates"]["C2_p95"]),
            passed=True,
            preregistered_in=ADR032_CERT,
        ),
    )
    sp = speed["speedup"]
    gates_speed = (
        GateVerdict(
            name="genuine-wins-in-2-of-3-seeds",
            gated=True,
            criterion="S6 as the record applies it: the surrogate arm wins a seed only if it "
            "searched (>= 1 marginal eval) AND used fewer marginal evals than direct-CFD BO; "
            "GO needs >= 2 of 3 seeds",
            comparator="ge",
            threshold=2.0,
            observed=float(sp["genuine_wins"]),
            passed=False,
            preregistered_in=ADR032_S6,
        ),
        GateVerdict(
            name="literal-marginal-wins",
            gated=False,
            criterion="literal S6 count, fewer marginal evals in >= 2 of 3 seeds (reported: the "
            "surrogate arm spent 0 marginal evals in every seed because the corpus already held "
            "the bar, so this count is degenerate)",
            comparator="ge",
            threshold=2.0,
            observed=float(sp["literal_marginal_wins"]),
            passed=True,
        ),
    )
    limitations = [
        *_common_limitations(src),
        _flagship_limitation(),
        _lim("tier-capped", v["V2_tier_cap_reason"], speed_ref, kind="quote"),
        _lim(
            "speedup-nogo",
            "No genuine single-run acceleration is demonstrated; fall back to direct-CFD BO (S7).",
            speed_ref,
            kind="quote",
        ),
        _lim(
            "nogo",
            "The pre-registered speed-up is a DEGENERATE NO-GO: the 42-solve corpus already "
            "held 5 designs past the bar, so the surrogate arm performed no marginal search.",
            speed_ref,
        ),
        _lim(
            "surrogate-proposals-smoke-tier",
            "The loop's proposals came from smoke-tier, in-loop retrained ensembles, by design "
            "(ADR-032): the proposing iteration's certificate had held-out p95 8.21 and coverage "
            "0.75. Every proposal was CFD-verified. The validated certificate is a separate fit.",
            explore_ref,
        ),
        _lim(
            "margin-inside-u95",
            "46.372 exceeds the corpus best 46.337 by 0.035, far inside the quantity's U95 of "
            "7.03, and is not claimed. The claim that clears 2 x U95 is against the BASELINE.",
            src,
        ),
        _lim(
            "held-out-is-same-grid-re-solve",
            "'Held out' means a deterministic same-grid re-solve that reproduces the loop's value "
            "bit for bit. It re-confirms the value; it adds no resolution.",
            speed_ref,
        ),
        _lim(
            "recorded-not-re-derivable",
            "u95_delta = 2.075 comes from 2-grid solves (s17v_base_coarse, s17v_opt_coarse) whose "
            "values and the baseline's four-tuple were not committed: recorded, not re-derivable.",
            src,
        ),
        _lim(
            "certificate-expiry",
            f"The validated surrogate certificate expires {cert['certificate']['expires_at']}.",
            cert_ref,
        ),
        _lim(
            "certificate-data-gate-content-blind",
            "The certificate's training_dataset_dvc_hash is sha256('{}'), the in-sync DVC status "
            "digest, not a content hash. This crate carries corpus.json itself and its md5.",
            cert_ref,
        ),
        _lim(
            "diagnostic-not-gate",
            "Gates marked gated decided the verdicts. The rest are reported diagnostics, "
            "including the margin over the corpus best and the proposer's certificate.",
            src,
        ),
    ]
    return CrateSpec(
        crate_id=crate_id,
        title="Stage 17: surrogate-accelerated airfoil optimization (validated, airfoil only)",
        description="A surrogate-proposed, CFD-verified airfoil optimum: L/D 46.372 vs baseline "
        "21.674, delta 24.70 > 2 x U95_delta = 4.15 (2-grid GCI), capped at validated. Certificate "
        "promoted to validated; the speed-up is a degenerate NO-GO. Airfoil only.",
        date_published=DATE,
        creators=CREATORS,
        runs=(
            _available(
                crate_id,
                "s17v_opt_fine",
                ("record-of-provenance", "cfd-verification"),
                result.provenance.model_dump(mode="json"),
                "v0.0.17",
                "CFD verification of the surrogate-proposed optimum (fine grid)",
            ),
        ),
        validity=ValidityContext(
            claim_tier="validated",
            claim_scope="optimization",
            flagship_domain=False,
            validated_against_experiment=False,
            verdicts=(
                Verdict(scope="optimization-claim", overall="GO", gates=gates_claim),
                Verdict(scope="surrogate-certificate", overall="GO", gates=gates_cert),
                Verdict(
                    scope="speed-up", overall="NO-GO", qualifier="degenerate", gates=gates_speed
                ),
            ),
            design_space=AIRFOIL_SPACE,
            conditions=AIRFOIL_CONDITIONS,
            certificate_expiry=cert["certificate"]["expires_at"],
            limitations=tuple(limitations),
        ),
        result=result,
        configs=(cfg,),
        evidence=(
            _evidence("data/vv/stage17_optimization.json", "the committed record"),
            _evidence(
                "data/vv/stage17_speedup.json", "the speed-up verdict and the V1/V2 verification"
            ),
            _evidence(
                "data/vv/stage17_surrogate_cert.json",
                "the validated certificate and its C1/C2 gates",
            ),
            _evidence(
                "data/vv/stage17_surrogate_cert_v2_refused.json", "the refused v2 re-certification"
            ),
            _evidence(
                "data/vv/stage17_arm_surrogate_explore.json", "the exploratory loop (16 CFD evals)"
            ),
            _evidence(
                corpus_rel, f"the 42-solve training corpus (DVC md5 {dvc_md5})", name="corpus.json"
            ),
        ),
        references=(
            src,
            speed_ref,
            cert_ref,
            explore_ref,
            _container_ref(),
            ADR032_CERT,
            _ref("dataset", f"{corpus_rel}.dvc"),
            _ref(
                "handoff",
                "docs/handoffs/STAGE-17-surrogate-accelerated-optimization-DONE-2026-07-24.md",
            ),
        ),
        unavailable=(
            Unavailable(
                item="baseline_provenance", reason="the s17v_base_fine four-tuple was not recorded"
            ),
            Unavailable(item="grid_inputs", reason="the 2-grid coarse solves were not committed"),
        ),
    )


REGISTRY: dict[str, Callable[[], CrateSpec]] = {
    "stage12-oscillating-cylinder-lockin": stage12,
    "stage14-rigid-flapping-wbd2004": stage14,
    "stage15-airfoil-optimization": stage15,
    "stage16-airfoil-grid-certification": stage16,
    "stage17-surrogate-accelerated-optimization": stage17,
}
# Committed records deliberately NOT crated, with the reason (never silently omitted).
EXCLUDED = {
    "data/vv/stage13_reportable_plunging_airfoil_hg2007_*.json (4)": "schema drift: written before "
    "the u95_input_basis validator; refused by the legacy import, never 'fixed'",
    "data/vv/stage14_lev_flapping_wing_wbd2004.png": "a qualitative LEV figure; the crate makes no "
    "claim it would support",
    "data/vv/stage16_optimization.json, stage16_grid_convergence.json": "the superseded steady "
    "graded campaign (cited by the Stage-16 crate, not embedded)",
    "data/vv/stage16_{courant_diag,divergence_diag,urans_convergence,urans_pathology,urans_probe}.json": (
        "Stage-16 attribution diagnostics behind the relaxation route, not results"
    ),
    "data/vv/stage17_arm_{direct,surrogate}_s{0,1,2}.json": "the per-seed speed-up arms, summarized "
    "by the embedded stage17_speedup.json",
    "data/vv/stage18_*.json, stage19_*.json, stage20_*.json": "not crated at v0.1.0 (a later ADR)",
}


def _readme(digests: dict[str, tuple[str, str, str]]) -> str:
    rows = "\n".join(
        f"| `{cid}` | {tier} | {verdicts} | `{digest}` |"
        for cid, (tier, verdicts, digest) in sorted(digests.items())
    )
    excluded = "\n".join(f"- `{k}`: {v}" for k, v in EXCLUDED.items())
    return f"""# Result crates (v0.1.0)

Self-describing, portable results: the RESULTS-MUST-TRAVEL bundle (Hard Rule 16), in
`aero-result-crate` format 1 (ADR-047). Each directory verifies and reads back to the same numbers
with nothing installed but Python, numpy and pydantic: no cluster, no DVC remote, no MLflow.
Content licence: CC-BY-4.0.

**What v0.1.0 does NOT claim.** The optimizer has never been run on a flapping-wing case, and
v0.1.0 makes no flapping-wing optimization claim. The optimizer is demonstrated on the airfoil
case only (Stages 15/16/17, validated tier, gate-honest). The flagship flapping domain is Stage
14's forward capability: its rotation-timing ordering is reproduced as a non-gated diagnostic, and
its gated mean lift is a NO-GO.

| crate | claim tier | verdicts | crate digest (sha256 of SHA256SUMS) |
|---|---|---|---|
{rows}

## Verify

```sh
sha256sum -c SHA256SUMS                      # inside a crate: coreutils only
python -I -B -m aero.crate verify crates/stage*  # full check (the aero wheel + numpy + pydantic)
python -I -B -m aero.crate show crates/<id>    # what it does and does not claim
```

Cite a result by its crate digest and its four-tuple.

## Not crated

{excluded}

Generated by `scripts/stage21_export_crates.py write`; do not edit by hand.
"""


def _summary(spec: CrateSpec, digest: str) -> tuple[str, str, str]:
    tier = (
        "NO CLAIM (evidence only)"
        if spec.validity.claim_tier == "none"
        else spec.validity.claim_tier
    )
    return tier, _verdicts_line(spec.validity), digest


def cmd_write(only: str | None, replace: bool) -> int:
    CRATES.mkdir(exist_ok=True)
    digests: dict[str, tuple[str, str, str]] = {}
    for crate_id, builder in REGISTRY.items():
        spec = builder()
        assert spec.crate_id == crate_id
        members = build_crate(spec)
        if only is None or only == crate_id:
            verified = write_crate(CRATES / crate_id, members, replace=replace)
            print(f"wrote {crate_id}  {verified.digest}")
        digests[crate_id] = _summary(
            spec, verify_crate(CRATES / crate_id).digest if (CRATES / crate_id).exists() else ""
        )
    (CRATES / "README.md").write_text(_readme(digests), encoding="utf-8", newline="\n")
    return 0


def _verdicts_line(validity: ValidityContext) -> str:
    return (
        ", ".join(
            f"{v.scope} {v.overall}{' (' + v.qualifier + ')' if v.qualifier else ''}"
            for v in validity.verdicts
        )
        or "-"
    )


def _git_problems(crate_id: str, code: CodeIdentity) -> list[str]:
    """Re-measure a run's declared code identity against git (needs full history and the tags)."""
    out: list[str] = []
    exists = (
        subprocess.run(
            ["git", "cat-file", "-e", f"{code.git_sha}^{{commit}}"],
            cwd=REPO,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )
    if not exists:
        if code.publicly_resolvable:
            out.append(f"{crate_id}: {code.git_sha} is declared public but is not in this clone")
        return out  # a declared-private commit is legitimately absent
    for ref in code.public_refs:
        tag = ref.removeprefix("refs/tags/")
        held = (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", code.git_sha, tag],
                cwd=REPO,
                capture_output=True,
                check=False,
            ).returncode
            == 0
        )
        if not held:
            out.append(f"{crate_id}: {ref} does not contain {code.git_sha}")
    if code.equivalent_tag is not None:
        if _tag_commit(code.equivalent_tag) != code.equivalent_tag_commit:
            out.append(
                f"{crate_id}: {code.equivalent_tag} no longer points at {code.equivalent_tag_commit}"
            )
        differing = tuple(
            p
            for p in _git(
                "diff",
                "--name-only",
                code.git_sha,
                code.equivalent_tag_commit or "",
                "--",
                *CODE_PATHS,
            ).splitlines()
            if p
        )
        if differing != code.differing_paths:
            out.append(
                f"{crate_id}: {code.git_sha[:12]} vs {code.equivalent_tag}: code paths differ in "
                f"{differing}, the crate declares {code.differing_paths}"
            )
    return out


def check_committed(*, git: bool) -> tuple[list[str], dict[str, tuple[str, str, str]]]:
    """Every problem with the committed crates, and their README rows. Never re-runs a recipe."""
    problems: list[str] = []
    present = sorted(p.name for p in CRATES.iterdir() if p.is_dir())
    if present != sorted(REGISTRY):
        return [f"crates/ holds {present}, the registry names {sorted(REGISTRY)}"], {}
    rows: dict[str, tuple[str, str, str]] = {}
    for crate_id in sorted(REGISTRY):
        v = verify_crate(CRATES / crate_id)
        if v.manifest.crate_id != crate_id:
            problems.append(f"crates/{crate_id} holds crate {v.manifest.crate_id!r}")
        for ref in v.manifest.references:
            # Every embedded evidence copy is the committed repository file, byte for byte.
            if (
                ref.embedded_as is not None
                and (REPO / ref.locator).read_bytes() != v.members[ref.embedded_as]
            ):
                problems.append(f"{crate_id}: {ref.embedded_as} != {ref.locator}")
        for member in v.manifest.members:
            if member.path == "evidence/corpus.json":
                dvc = (REPO / "data/datasets/stage17_naca4_ld/corpus.json.dvc").read_text(
                    encoding="utf-8"
                )
                want = re.search(r"md5: ([0-9a-f]{32})", dvc)
                got = hashlib.md5(v.members[member.path], usedforsecurity=False).hexdigest()
                if want is None or got != want.group(1):
                    problems.append(
                        f"{crate_id}: evidence/corpus.json md5 {got} != its DVC pointer"
                    )
        if git:
            for run in v.manifest.runs:
                if isinstance(run.provenance, ProvenanceAvailable):
                    problems.extend(_git_problems(crate_id, run.provenance.code))
        tier = v.manifest.validity.claim_tier
        rows[crate_id] = (
            "NO CLAIM (evidence only)" if tier == "none" else tier,
            _verdicts_line(v.manifest.validity),
            v.digest,
        )
    if (CRATES / "README.md").read_text(encoding="utf-8") != _readme(rows):
        problems.append("crates/README.md is stale: rerun `write`")
    return problems, rows


def cmd_check(git: bool) -> int:
    """Verify the committed crates (see the module docstring)."""
    problems, rows = check_committed(git=git)
    for crate_id, (_, _, digest) in sorted(rows.items()):
        print(
            f"OK  {crate_id}  {digest}"
            if not any(p.startswith(crate_id) for p in problems)
            else f"BAD {crate_id}"
        )
    for line in problems:
        print(f"PROBLEM: {line}", file=sys.stderr)
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write")
    w.add_argument("--crate", choices=sorted(REGISTRY))
    w.add_argument("--replace", action="store_true")
    c = sub.add_parser("check")
    c.add_argument(
        "--no-git", action="store_true", help="skip the code-identity checks (shallow clones)"
    )
    a = ap.parse_args(argv)
    if a.cmd == "write":
        return cmd_write(a.crate, a.replace)
    return cmd_check(git=not a.no_git)


if __name__ == "__main__":
    sys.exit(main())

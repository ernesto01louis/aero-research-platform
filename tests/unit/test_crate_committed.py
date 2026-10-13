"""The five committed v0.1.0 result crates (Stage 21, ADR-047 D7): a regression corpus.

They must keep verifying with every later version of the reader. If a validator tightening
rejects one, this file goes red. That forces an explicit decision (stay backward compatible, or
re-issue under an ADR); a crate is never silently regenerated.

The era recipes are NOT re-run here (scripts/stage21_export_crates.py `write` is one-shot). These
tests check the committed bytes against:
- the committed records;
- an independent stdlib oracle;
- the platform's own GCI and certificate code.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from aero.crate import VerifiedCrate, verify_crate
from aero.crate.model import ProvenanceAvailable
from aero.crate.validity import FLAGSHIP_LIMITATION_SENTENCE

pytestmark = pytest.mark.stage_21

REPO = Path(__file__).resolve().parents[2]
CRATES = REPO / "crates"
L1 = "The optimizer has never been run on a flapping-wing case."


def _script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


EXPORT = _script("stage21_export_crates")
ORACLE = _script("crate_oracle")
IDS = sorted(EXPORT.REGISTRY)


@pytest.fixture(scope="module")
def crates() -> dict[str, VerifiedCrate]:
    return {crate_id: verify_crate(CRATES / crate_id) for crate_id in IDS}


def test_the_committed_set_is_exactly_the_registry() -> None:
    assert sorted(p.name for p in CRATES.iterdir() if p.is_dir()) == IDS
    assert sorted(ORACLE.DIGESTS) == IDS


def test_every_crate_is_consistent_with_the_repository() -> None:
    # Evidence == the committed files; corpus md5 == its DVC pointer; README digest table current.
    # Code identity against git runs in crate-roundtrip (full history); not here (shallow clone).
    problems, _ = EXPORT.check_committed(git=False)
    assert problems == []


@pytest.mark.parametrize("crate_id", IDS)
def test_digests_are_pinned(crates: dict[str, VerifiedCrate], crate_id: str) -> None:
    assert crates[crate_id].digest == ORACLE.DIGESTS[crate_id]
    assert crates[crate_id].manifest.crate_id == crate_id


def test_the_independent_oracle_agrees_bit_for_bit(crates: dict[str, VerifiedCrate]) -> None:
    oracle = ORACLE.build(REPO)
    got = {crate_id: v.numbers() for crate_id, v in crates.items()}
    assert ORACLE.compare(oracle, got) == []
    # ... and it would notice a single-ulp change.
    ptr = "/quantities/0/value"
    s17 = got["stage17-surrogate-accelerated-optimization"]
    value = float.fromhex(s17["result"][ptr][1])
    s17["result"][ptr] = ["float", (value + value * 2**-52).hex()]
    assert any(ptr in line for line in ORACLE.compare(oracle, got))


def test_headline_numbers(crates: dict[str, VerifiedCrate]) -> None:
    s12 = crates["stage12-oscillating-cylinder-lockin"].result
    assert s12 is not None and s12.validation_tag == "thesis-grade"
    assert s12.quantities[0].value == 1.9931465473474796
    assert s12.quantities[0].u95_total == 0.07858093411968879
    s17 = crates["stage17-surrogate-accelerated-optimization"].result
    assert s17 is not None and s17.optimization is not None
    assert s17.quantities[0].value == 46.37208685252852
    assert s17.optimization.improvement.delta == 24.6980545297548
    assert s17.optimization.improvement.required_margin == 4.15005727858274


def test_stage14_is_evidence_only_with_no_claim(crates: dict[str, VerifiedCrate]) -> None:
    v = crates["stage14-rigid-flapping-wbd2004"]
    assert v.result is None and v.manifest.payload == "none"
    assert v.manifest.validity.claim_tier == "none" and v.manifest.validity.flagship_domain
    assert [x.overall for x in v.manifest.validity.verdicts] == ["NO-GO"]
    assert all(not isinstance(r.provenance, ProvenanceAvailable) for r in v.manifest.runs)
    gated = [g for x in v.manifest.validity.verdicts for g in x.gates if g.gated]
    assert [(g.name, g.threshold, g.passed) for g in gated] == [
        ("symmetrical-mean-lift-within-band", 0.25, False)
    ]


@pytest.mark.parametrize("crate_id", IDS)
def test_no_crate_claims_flapping_optimization(
    crates: dict[str, VerifiedCrate], crate_id: str
) -> None:
    validity = crates[crate_id].manifest.validity
    assert not (validity.flagship_domain and validity.claim_scope == "optimization")
    if validity.claim_scope == "optimization" or validity.flagship_domain:
        text = " ".join(lim.text for lim in validity.limitations)
        assert L1 in text and FLAGSHIP_LIMITATION_SENTENCE in text


def test_verdicts_are_record_faithful(crates: dict[str, VerifiedCrate]) -> None:
    def overall(crate_id: str) -> dict[str, tuple[str, str | None]]:
        return {
            v.scope: (v.overall, v.qualifier) for v in crates[crate_id].manifest.validity.verdicts
        }

    assert overall("stage12-oscillating-cylinder-lockin") == {"thesis-grade-gate": ("GO", None)}
    assert overall("stage15-airfoil-optimization") == {"optimization-claim": ("NO-GO", None)}
    assert overall("stage16-airfoil-grid-certification") == {"grid-certification": ("NO-GO", None)}
    assert overall("stage17-surrogate-accelerated-optimization") == {
        "optimization-claim": ("GO", None),
        "surrogate-certificate": ("GO", None),
        "speed-up": ("NO-GO", "degenerate"),
    }
    s16 = crates["stage16-airfoil-grid-certification"].manifest.validity.verdicts[0]
    assert [g.name for g in s16.gates if g.gated and not g.passed] == ["order-in-asymptotic-range"]


def _record(name: str) -> Any:
    return json.loads((REPO / "data" / "vv" / f"{name}.json").read_text(encoding="utf-8"))


def _gates(v: VerifiedCrate) -> dict[str, Any]:
    return {g.name: g for x in v.manifest.validity.verdicts for g in x.gates}


@pytest.mark.parametrize(
    ("crate_id", "record", "significant_gate"),
    [
        ("stage15-airfoil-optimization", "stage15_grid_convergence", "delta-exceeds-k-u95"),
        ("stage16-airfoil-grid-certification", "stage16_relaxed_convergence", "significant"),
    ],
)
def test_the_grid_gates_re_derive_from_the_recorded_solves(
    crates: dict[str, VerifiedCrate], crate_id: str, record: str, significant_gate: str
) -> None:
    """The platform's own 3-grid GCI, run on the recorded per-grid L/D, gives the crate's gates."""
    from aero.optimize.report import MatchedGridDeltaTriplet, certification_gates

    conv = _record(record)
    ld = {(r["design"], r["grid"]): r["ld"] for r in conv["solves"]}
    triplet = MatchedGridDeltaTriplet(
        quantity="lift_to_drag",
        **{
            f"{d}_{g}": ld[(d, g)]
            for d in ("baseline", "optimum")
            for g in ("fine", "medium", "coarse")
        },
        refinement_ratio=conv["refinement_ratio"],
        u95_delta_iterative=conv["u95_delta_iterative"],
    )
    gates = _gates(crates[crate_id])
    assert gates[significant_gate].observed == triplet.delta_fine
    # Transcendental (log/pow) results may differ in the last ulp across libms: compare tightly,
    # not bitwise. The crates carry the RECORDED values, which the oracle pins bitwise.
    assert gates[significant_gate].threshold == pytest.approx(
        2.0 * triplet.u95_delta_numerical, rel=1e-12
    )
    order_gate = (
        "order-in-asymptotic-range"
        if "order-in-asymptotic-range" in gates
        else "observed-order-in-asymptotic-range"
    )
    assert gates[order_gate].observed == pytest.approx(triplet.observed_order_delta, rel=1e-12)
    if "gates" in conv:
        derived = certification_gates(
            triplet, all_converged=conv["all_converged_claim_grids"], higher_is_better=True
        )
        assert derived == conv["gates"]
        assert gates["significant"].passed is derived["significant"]
        assert gates["order-in-asymptotic-range"].passed is derived["order_in_asymptotic_range"]


def test_the_stage17_certificate_gates_re_derive_from_the_certificate(
    crates: dict[str, VerifiedCrate],
) -> None:
    from aero.surrogates._common.certificate import CertificateOfValidity

    cert = CertificateOfValidity.model_validate(_record("stage17_surrogate_cert")["certificate"])
    assert cert.cert_status == "validated"
    gates = _gates(crates["stage17-surrogate-accelerated-optimization"])
    assert cert.uncertainty_calibration is not None
    assert gates["c1-coverage-in-band"].observed == cert.uncertainty_calibration.empirical_coverage
    assert gates["c2-p95-within-bar"].observed == cert.held_out_metrics["ld_mae"].p95
    v = crates["stage17-surrogate-accelerated-optimization"]
    assert v.manifest.validity.certificate_expiry == cert.expires_at


def test_action_ids_are_unique_and_containers_are_recorded(
    crates: dict[str, VerifiedCrate],
) -> None:
    ids = [r.action_id for v in crates.values() for r in v.manifest.runs]
    assert len(ids) == len(set(ids))
    sums = (REPO / "containers" / "SHA256SUMS").read_text(encoding="utf-8").split()
    for v in crates.values():
        for ref in v.manifest.references:
            if ref.role == "container":
                assert ref.sha256 in sums and ref.locator in sums


def test_no_crate_lives_under_data_vv_and_the_adr045_records_stay_absent() -> None:
    assert not list((REPO / "data" / "vv").glob("**/aero-crate.json"))
    assert not (REPO / "data/vv/stage20_adr045_r3.json").exists()
    assert not (REPO / "data/vv/stage20_n3_confirmation.json").exists()

"""Tampering with a result crate is refused (ADR-047 D3).

Three attackers are tested:

* An outsider flips bytes. ``SHA256SUMS`` catches that.
* An insider edits a member and re-hashes ``SHA256SUMS``. The members table, the lossless rule,
  the config hash, the legacy replay or the projections catch that.
* An insider regenerates a whole edited crate. It verifies, but its digest differs, so the
  out-of-band ``expect_digest`` check catches it. That is the documented trust model:
  ``SHA256SUMS`` gives integrity, and the published crate digest gives authenticity.
"""

from __future__ import annotations

import json

import pytest
from aero.crate import (
    CrateError,
    CrateExpectationError,
    CrateIntegrityError,
    build_crate,
    verify_members,
)
from aero.crate._canonical import dumps_document, loads_strict, sha256_hex
from aero.crate.members import SUMS, format_sha256sums
from aero.vv.reportable import ReportableQuantity

from tests.unit._crate_fixtures import SHAPES, built, steady_optimization

pytestmark = pytest.mark.stage_21


def _resum(members: dict[str, bytes]) -> dict[str, bytes]:
    out = dict(members)
    out[SUMS] = format_sha256sums({p: sha256_hex(b) for p, b in out.items() if p != SUMS})
    return out


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_a_flipped_byte_in_any_member_is_caught(shape: str) -> None:
    members = built(shape)
    for name in members:
        if name == SUMS:
            continue
        tampered = dict(members)
        data = bytearray(tampered[name])
        data[len(data) // 2] ^= 0x01
        tampered[name] = bytes(data)
        with pytest.raises(CrateIntegrityError):
            verify_members(tampered)


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_a_missing_or_extra_member_is_caught(shape: str) -> None:
    members = built(shape)
    for name in [n for n in members if n != SUMS]:
        with pytest.raises(CrateError):
            verify_members({k: v for k, v in members.items() if k != name})
    extra = dict(members)
    extra["evidence/extra.txt"] = b"smuggled\n"
    with pytest.raises(CrateIntegrityError):
        verify_members(extra)
    with pytest.raises(CrateError):
        verify_members(_resum(extra))


def test_an_insider_edit_with_rehashed_sums_is_caught_by_the_members_table() -> None:
    members = built("steady_optimization")
    doc = loads_strict(members["result.json"], what="result.json")
    doc["quantities"][0]["value"] = 99.0
    members["result.json"] = dumps_document(doc)
    with pytest.raises(CrateError, match="members table"):
        verify_members(_resum(members))


def test_an_insider_edit_of_result_and_table_is_caught_by_the_payload_rule() -> None:
    members = built("steady_optimization")
    doc = loads_strict(members["result.json"], what="result.json")
    doc["optimization"]["improvement"]["required_margin"] = 0.001  # a forged computed value
    members["result.json"] = dumps_document(doc)
    manifest = loads_strict(members["aero-crate.json"], what="aero-crate.json")
    for entry in manifest["members"]:
        if entry["path"] == "result.json":
            entry["sha256"] = sha256_hex(members["result.json"])
            entry["size"] = len(members["result.json"])
    members["aero-crate.json"] = dumps_document(manifest)
    with pytest.raises(CrateError, match=r"not reproduced|projection|faithful"):
        verify_members(_resum(members))


def test_an_edited_config_preimage_is_caught() -> None:
    members = built("steady_optimization")
    path = next(p for p in members if p.startswith("configs/"))
    cfg = json.loads(members[path])
    cfg["reynolds"] = 1.0
    members[path] = json.dumps(cfg, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(CrateError):
        verify_members(_resum(members))


def test_a_fully_regenerated_edited_crate_fails_only_the_expected_digest() -> None:
    honest = verify_members(built("steady_optimization"))
    spec = steady_optimization()
    assert spec.result is not None
    forged_result = spec.result.model_copy(
        update={
            "quantities": (
                ReportableQuantity(name="L/D", value=48.0, u95_numerical=7.033600211508836),
            )
        }
    )
    from dataclasses import replace

    forged_ref = tuple(r for r in spec.references if r.role != "source-record")
    forged_members = build_crate(
        replace(spec, result=forged_result, evidence=(), references=forged_ref)
    )
    forged = verify_members(forged_members)  # it is internally consistent...
    assert forged.digest != honest.digest
    with pytest.raises(CrateExpectationError):
        verify_members(forged_members, expect_digest=honest.digest)  # ...but not the published one
    verify_members(built("steady_optimization"), expect_digest=honest.digest)


def test_a_result_that_does_not_match_its_embedded_source_record_is_refused() -> None:
    from dataclasses import replace

    spec = steady_optimization()
    assert spec.result is not None
    other = spec.result.model_copy(update={"case_name": "renamed"})
    with pytest.raises(CrateError, match="faithful import"):
        build_crate(replace(spec, result=other))

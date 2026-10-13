"""The v0.1.0 paper and release notes say only what the crates carry (operator decision D2; ADR-046).

Every number in docs/release/claims-ledger.toml is re-derived from a verified crate and must
match the text exactly. The ADR-046 limitation must sit in the BODY of both documents.
Record-faithful phrases are required, and over-claims are forbidden.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
from aero.crate import VerifiedCrate, verify_crate

pytestmark = pytest.mark.stage_21

REPO = Path(__file__).resolve().parents[2]
LEDGER = tomllib.loads((REPO / "docs/release/claims-ledger.toml").read_text(encoding="utf-8"))
DOCS = {"paper": REPO / LEDGER["paper"], "notes": REPO / LEDGER["notes"]}
L1 = (
    "The optimizer has never been run on a flapping-wing case, and v0.1.0 makes no flapping-wing "
    "optimization claim."
)
REQUIRED_IN_NOTES = (
    "a pre-registered, non-gated diagnostic",
    "a documented NO-GO; the band was not relaxed",
    "the leading hypothesis",
    "smoke-tier, in-loop retrained ensembles",
    "every\nproposal was CFD-verified",
    "same-grid re-solve",
    "degenerate NO-GO",
    "no experiment anchor",
    "The only thesis-grade record is Stage 12",
)
FORBIDDEN = (
    "root-caused",
    "+47",
    "thesis-grade improvement",
    "certified optimum",
    "topology optimizer",
    "shape/topology",
    "neural operator",
    "Surrogates accelerate",
    "validated ensemble drove",
    "trend VALIDATED",
    "trend is VALIDATED",
)
_CRATES: dict[str, VerifiedCrate] = {}


def _crate(crate_id: str) -> VerifiedCrate:
    if crate_id not in _CRATES:
        _CRATES[crate_id] = verify_crate(REPO / "crates" / crate_id)
    return _CRATES[crate_id]


def _at(doc: Any, pointer: str) -> Any:
    for part in pointer.strip("/").split("/"):
        doc = doc[int(part)] if isinstance(doc, list) else doc[part]
    return doc


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _body(markdown: str) -> str:
    cut = re.search(r"^#{1,3}\s+(Acknowledg|References)", markdown, re.M)
    text = markdown[: cut.start()] if cut else markdown
    return "\n".join(ln for ln in text.splitlines() if not re.match(r"^\[\^[^\]]+\]:", ln))


def _value(claim: dict[str, Any]) -> Any:
    v = _crate(claim["crate"])
    if "result" in claim:
        assert v.result is not None
        return _at(json.loads(v.members["result.json"]), claim["result"])
    if "gate" in claim:
        scope, name = claim["gate"].split("/", 1)
        verdict = next(x for x in v.manifest.validity.verdicts if x.scope == scope)
        gate = next(g for g in verdict.gates if g.name == name)
        if claim["attr"] == "threshold-low":
            assert isinstance(gate.threshold, tuple)
            return gate.threshold[0]
        return getattr(gate, claim["attr"])
    return _at(json.loads(v.members[claim["member"]]), claim["pointer"])


@pytest.mark.parametrize("claim", LEDGER["claim"], ids=[c["id"] for c in LEDGER["claim"]])
def test_every_stated_number_comes_from_a_crate(claim: dict[str, Any]) -> None:
    value = _value(claim)
    if isinstance(value, float):
        value *= claim.get("scale", 1.0)
    assert claim["format"].format(value) == claim["text"]
    for doc in claim["in"]:
        assert claim["text"] in _flat(_body(DOCS[doc].read_text(encoding="utf-8"))), (
            claim["id"],
            doc,
        )


@pytest.mark.parametrize("doc", sorted(DOCS))
def test_the_limitation_is_in_the_body(doc: str) -> None:
    assert L1 in _flat(_body(DOCS[doc].read_text(encoding="utf-8")))


def test_the_paper_states_it_in_the_summary_and_the_limitations_section() -> None:
    text = DOCS["paper"].read_text(encoding="utf-8")
    sections = dict(re.findall(r"^# (.+?)\n(.*?)(?=^# |\Z)", text, re.M | re.S))
    assert L1 in _flat(sections["Summary"])
    assert L1 in _flat(sections["Demonstrated scope and limitations at v0.1.0"])


@pytest.mark.parametrize("phrase", REQUIRED_IN_NOTES)
def test_the_notes_carry_the_record_faithful_phrases(phrase: str) -> None:
    assert _flat(phrase) in _flat(_body(DOCS["notes"].read_text(encoding="utf-8")))


@pytest.mark.parametrize(
    "rel", [*(LEDGER[k] for k in ("paper", "notes")), "CITATION.cff", ".zenodo.json"]
)
def test_no_over_claim(rel: str) -> None:
    text = (REPO / rel).read_text(encoding="utf-8")
    assert [p for p in FORBIDDEN if p in text] == []


def test_the_notes_list_every_crate_digest() -> None:
    notes = DOCS["notes"].read_text(encoding="utf-8")
    for d in sorted((REPO / "crates").glob("stage*")):
        assert verify_crate(d).digest in notes, d.name

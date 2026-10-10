"""Two records must NEVER exist, and their absence is load-bearing.

ADR-041 V7 FIRED (2026-09-20): the gated campaign is a recorded NO-GO on infrastructure, so
no N3 confirmation and no R3 verdict can ever be produced honestly.

The R3 record is not merely absent — the R7 gate refuses a gated restarted solve **by** its
absence (``_assert_restart_admissible`` in the driver), so creating the file, even empty or
hand-written, would silently re-open a path the NO-GO closed. The B2/B1/B3 sentinels are
machine-gated on the N3 record in the same way. ADR-039's ``<<B2-PENDING-I4>>`` has the same
shape and is pinned by ``test_adr039_b2_marker_state.py``; this is that idiom applied to the
two records the NO-GO makes permanent.

A future session that legitimately reopens the campaign (a NEW ADR and the operator's word —
see ADR-045's "R6 — EXECUTED" for what is and is not ruled out) deletes this test deliberately,
as part of that ADR. It does not quietly add the files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
_NOGO = _REPO_ROOT / "data/vv/stage20_nogo_infrastructure.json"
_MUST_NOT_EXIST = (
    _REPO_ROOT / "data/vv/stage20_adr045_r3.json",
    _REPO_ROOT / "data/vv/stage20_n3_confirmation.json",
)


@pytest.mark.parametrize("path", _MUST_NOT_EXIST, ids=lambda p: p.name)
def test_the_record_stays_absent(path: Path) -> None:
    assert not path.exists(), (
        f"{path.name} exists. Under the Stage-20 NO-GO (ADR-041 V7 FIRED, handoff 6.89) it can "
        "carry no honest verdict: R3 was never evaluable (ADR-045 A19) and no gated wave ran. "
        "Its ABSENCE is what makes the R7 gate refuse a gated restarted solve. If the campaign "
        "was legitimately reopened by a new ADR, delete this test in that ADR's commit."
    )


def test_the_nogo_record_exists_and_names_both_absences() -> None:
    """The prohibition and the verdict travel together, or neither is auditable."""
    import json

    assert _NOGO.exists(), "the NO-GO verdict record is missing"
    record = json.loads(_NOGO.read_text(encoding="utf-8"))
    assert record["verdict"] == "NO-GO-on-infrastructure"
    assert record["clause"] == "ADR-041 V7"
    # `complete` because a NO-GO is a result (operator, 2026-10-10) -- NOT because the
    # deliverables were met; the record's own not_delivered list is what says that.
    assert record["status_after"] == "complete"
    assert record["not_delivered"], "a complete-with-NO-GO record must still name the misses"
    # R3 has NO verdict — not "fail" (ADR-045 A19)
    assert record["r3_outcome"]["verdict"] is None
    named = set(record["records_that_must_never_exist"])
    assert named == {str(p.relative_to(_REPO_ROOT)) for p in _MUST_NOT_EXIST}

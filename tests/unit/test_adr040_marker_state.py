"""ADR-040's three pending markers are pending XOR filled, and the sentinels track them.

ADR-039 B2 established the three-commit dance — the RULE now, the RECORD next, the
NUMBERS last — and the reason it is machine-checked is that the middle state is where a
hand edit is invisible: numbers typed into the ADR look exactly like numbers derived from
a measurement. ADR-040 has three such markers rather than one, and they pend on different
things:

* ``<<B1-PENDING-N3>>``   — the pre-flight ceiling, an OUTPUT of N3's measured post-ramp
  rate. ADR-039's B1 was never satisfiable and B1 says so.
* ``<<B2-PENDING-ADR040>>`` — the gated campaign, an output of the same record through
  ``size_gated_campaign_040``.
* ``<<B3-PENDING-CEILING>>`` — the per-wave ceiling, pending an OPERATOR DECISION taken
  against N3's measured rate. Its rule is pre-registered; only the number is deferred.

The fourth property here is the one that makes ADR-040 possible at all: **ADR-039's own
marker must still stand.** Two documents each with a pending B2 would be ambiguous; one
permanently pending and one live is the actual state, and it is asserted rather than
assumed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADR_039 = _REPO_ROOT / "docs/adrs/ADR-039-hg2007-flexible-foil-gate-preregistration.md"
_ADR_040 = _REPO_ROOT / "docs/adrs/ADR-040-campaign-numerics-re-preregistration.md"

_B1 = "<<B1-PENDING-N3>>"
_B2 = "<<B2-PENDING-ADR040>>"
_B3 = "<<B3-PENDING-CEILING>>"

_N3_RECORD = _REPO_ROOT / "data/vv/stage20_n3_confirmation.json"
_DERIVATION_TEST = _REPO_ROOT / "tests/unit/test_adr040_budget_is_derived_from_n3.py"


def _text() -> str:
    return _ADR_040.read_text(encoding="utf-8")


def _block() -> str:
    """The GATE BLOCK, not the whole file.

    ADR-040's prose names all three markers when it explains the three-commit discipline,
    so a whole-file count is 2 for a pending marker and 1 for a filled one — the exact
    inversion of what it is supposed to mean. The pre-registration is the block; the prose
    is commentary about it, and ``test_no_marker_lingers_in_the_prose_after_a_fill`` keeps
    the commentary from going stale.
    """
    text = _text()
    fenced = (
        text.split("<!-- GATE-BLOCK-040:BEGIN -->", 1)[1]
        .split("<!-- GATE-BLOCK-040:END -->", 1)[0]
        .strip()
    )
    return fenced.removeprefix("```text").removesuffix("```").strip("\n") + "\n"


def test_b1_is_pending_xor_derived_from_the_n3_record() -> None:
    text = _block()
    if _B1 in text:
        assert text.count(_B1) == 1, "the marker must appear exactly once, in B1"
        return
    assert _N3_RECORD.exists(), "B1 is filled but data/vv/stage20_n3_confirmation.json is missing"
    assert _DERIVATION_TEST.exists(), "B1 is filled but the derivation test is missing"


def test_b2_is_pending_xor_filled_as_an_output() -> None:
    text = _block()
    if _B2 in text:
        assert text.count(_B2) == 1, "the marker must appear exactly once, in B2"
        return
    assert _N3_RECORD.exists(), "B2 is filled but the N3 record is missing"
    assert _DERIVATION_TEST.exists(), "B2 is filled but the derivation test is missing"
    assert "time-window-size" in text.split("B2 gated campaign", 1)[1][:800]


def test_b3_is_pending_xor_carries_an_approved_ceiling() -> None:
    """B3 pends on a DECISION, not a derivation — so what it needs when filled differs.

    A ceiling is the one number here that no rule can produce on its own: the rule picks
    the smallest ceiling that fits 20 settled cycles at the measured rate, but whether the
    operator accepts a campaign that long is theirs. So a filled B3 must name the rate it
    was taken against, or it is a number with no provenance.
    """
    text = _block()
    if _B3 in text:
        assert text.count(_B3) == 1, "the marker must appear exactly once, in B3"
        return
    assert _N3_RECORD.exists(), "B3 is filled but the N3 record it was decided against is missing"
    b3 = text.split("B3 per-wave ceiling", 1)[1][:900]
    assert "s/window" in b3, "a filled B3 must state the measured rate it was taken against"


def test_the_adr040_sentinels_track_the_b2_marker() -> None:
    """All four arm the gate together; a partial fill would gate on two of four inputs."""
    from aero.vv.fsi.hg2007_flexible_foil import (
        GATED_040_MAX_TIME_S,
        GATED_040_MPI_RANKS,
        GATED_040_NUMERICS_LABEL,
        GATED_040_TIME_WINDOW_S,
    )

    sentinels = (
        GATED_040_TIME_WINDOW_S,
        GATED_040_MAX_TIME_S,
        GATED_040_NUMERICS_LABEL,
        GATED_040_MPI_RANKS,
    )
    if _B2 in _block():
        assert all(s is None for s in sentinels), (
            "an ADR-040 sentinel is filled while B2 is still pending — a configuration "
            "could claim the gated verdict before N3 ran"
        )
    else:
        assert all(s is not None for s in sentinels), (
            "B2 is filled but an ADR-040 sentinel is still None — the gate would compare "
            "against a missing input and nothing could ever be gated"
        )


def test_no_marker_lingers_in_the_prose_after_a_fill() -> None:
    """The cost of judging state on the block: the prose can go stale unnoticed.

    ADR-040's "Neutral / followup" paragraph names all three markers. Once a marker is
    filled in the block, a copy left behind in the prose says the number is still pending
    when it is not — the same class of stale-document error as a README STATUS block that
    nobody regenerates. Cheap to check, so it is checked.
    """
    block, text = _block(), _text()
    for marker in (_B1, _B2, _B3):
        if marker in block:
            continue
        assert marker not in text, (
            f"{marker} is filled in the gate block but still quoted in ADR-040's prose"
        )


def test_adr_039s_marker_stands_unfilled_permanently() -> None:
    """The premise ADR-040 U11 rests on, asserted rather than assumed.

    ADR-039's sentinels are also checked by ``test_adr039_b2_marker_state``; what is added
    here is the CROSS-document claim, which neither file's own test can make: exactly one
    of the two pre-registrations is live.
    """
    from aero.vv.fsi.hg2007_flexible_foil import GATED_MAX_TIME_S, GATED_TIME_WINDOW_S

    assert _ADR_039.read_text(encoding="utf-8").count("<<B2-PENDING-I4>>") == 1
    assert GATED_TIME_WINDOW_S is None and GATED_MAX_TIME_S is None
    assert "STANDS UNFILLED PERMANENTLY" in _text()

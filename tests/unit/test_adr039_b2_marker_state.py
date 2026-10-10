"""B2 carries ``<<B2-PENDING-I4>>`` XOR the derived numbers — never both, never neither.

The three-commit dance (rule now, record next, numbers last) is only honest if the
middle state is machine-checked: while the marker stands, no I4 record need exist; the
moment it is filled, the I4 record AND the derivation test that re-computes the numbers
from it must both exist, or the fill was a hand edit rather than an output.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADR = _REPO_ROOT / "docs/adrs/ADR-039-hg2007-flexible-foil-gate-preregistration.md"
_MARKER = "<<B2-PENDING-I4>>"
_I4_RECORD = _REPO_ROOT / "data/vv/stage20_i4_calibration.json"
_DERIVATION_TEST = _REPO_ROOT / "tests/unit/test_adr039_budget_is_derived_from_i4.py"


def test_b2_is_pending_xor_filled() -> None:
    text = _ADR.read_text(encoding="utf-8")
    pending = _MARKER in text
    if pending:
        assert text.count(_MARKER) == 1, "the marker must appear exactly once, in B2"
        return
    # Filled: the numbers must be an OUTPUT — the record and its derivation test exist.
    assert _I4_RECORD.exists(), "B2 is filled but data/vv/stage20_i4_calibration.json is missing"
    assert _DERIVATION_TEST.exists(), "B2 is filled but the derivation test is missing"
    assert "time-window-size" in text.split("B2 gated campaign", 1)[1][:600]


def test_the_gated_sentinels_track_the_marker() -> None:
    """The case module's sentinels arm the gate; they may be filled only when B2 is."""
    from aero.vv.fsi.hg2007_flexible_foil import GATED_MAX_TIME_S, GATED_TIME_WINDOW_S

    pending = _MARKER in _ADR.read_text(encoding="utf-8")
    if pending:
        assert GATED_TIME_WINDOW_S is None and GATED_MAX_TIME_S is None, (
            "the sentinels are filled while B2 is still pending — a configuration could "
            "claim the gated verdict before the pre-flight ran"
        )
    else:
        assert GATED_TIME_WINDOW_S is not None and GATED_MAX_TIME_S is not None, (
            "B2 is filled but the sentinels are still None — nothing could ever be gated"
        )

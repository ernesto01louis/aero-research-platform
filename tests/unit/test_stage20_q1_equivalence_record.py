"""Q1 accepted, on bands fixed before it ran — and the record says what it does NOT show.

The interesting number here is the third one. The two arms' span-mean forces reproduce the
ADR-039 baseline to 0.05 % and 0.002 %, which on its own reads as "the stacks are
identical". Their DIFFERENCE moves 3.5 %, because the increment is a small number between
two large ones and inherits both their errors. That is exactly why ADR-040 Q1 pre-registers
it as its own clause with its own band: a common-mode shift must not read as an increment
failure, and an anti-symmetric one must not read as a pass.

So this file pins the acceptance, pins that the bands are the ones the ADR states, and pins
that Q2's limits ride in the record rather than in a reader's memory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RECORD = _REPO_ROOT / "data/vv/stage20_q1_equivalence.json"
_ADR = _REPO_ROOT / "docs/adrs/ADR-040-campaign-numerics-re-preregistration.md"


def _record() -> dict:
    return json.loads(_RECORD.read_text(encoding="utf-8"))


def test_q1_accepted_on_all_three_clauses() -> None:
    record = _record()
    assert record["adr"] == "ADR-040"
    assert record["clause"] == "Q1-equivalence"
    assert record["gated"] is False
    assert record["clauses"] == {
        "Q1a_span_mean_per_arm": True,
        "Q1b_trace_per_arm": True,
        "Q1c_increment_of_span_means": True,
    }
    assert record["accepted"] is True


def test_the_bands_are_the_ones_the_adr_pre_registered() -> None:
    """A band the record invents is not a pre-registration."""
    bands = _record()["bands"]
    assert (bands["Q1a_span_mean"], bands["Q1b_trace_over_baseline_amplitude"]) == (0.02, 0.05)
    assert bands["Q1c_increment_of_span_means"] == 0.05
    adr = _ADR.read_text(encoding="utf-8")
    assert "within 2 percent of the baseline's span-mean" in adr
    assert "within 5 percent of the baseline trace's peak-to-peak amplitude" in adr


def test_both_arms_were_compared_against_the_surviving_adr039_runs() -> None:
    arms = _record()["arms"]
    assert set(arms) == {"flexible", "rigid"}
    assert arms["flexible"]["baseline_run_id"] == "hg2007_flexible_foil-20260810-144742"
    assert arms["rigid"]["baseline_run_id"] == "hg2007_rigid_foil-20260810-144747"
    for arm in arms.values():
        assert arm["n_windows_compared"] >= 500
        assert arm["candidate_run_id"] != arm["baseline_run_id"]


def test_each_arm_is_inside_its_own_band() -> None:
    for arm in _record()["arms"].values():
        assert arm["span_mean_relative_difference"] <= 0.02
        assert arm["trace_deviation_over_amplitude"] <= 0.05


def test_the_increment_is_the_clause_that_actually_had_room_to_fail() -> None:
    """Stated as an inequality so the point survives a future re-run with other numbers.

    If the increment's margin ever stops being the tightest of the three, the separate
    clause has stopped earning its place and someone should notice.
    """
    record = _record()
    increment = record["increment"]["relative_difference"]
    per_arm = max(a["span_mean_relative_difference"] for a in record["arms"].values())
    assert increment > 10 * per_arm, (
        "the increment no longer amplifies the per-arm agreement; re-read whether Q1c is "
        "still measuring what it was written to measure"
    )
    assert increment <= 0.05


def test_the_record_carries_q2s_limits_and_the_rejection_outcome() -> None:
    record = _record()
    assert "INSIDE the ramp" in record["q2_limits"]
    assert "AS DELIVERED" in record["q2_limits"]
    assert "does not localize" in record["q2_limits"]
    assert "INADMISSIBLE" in record["rejection_outcome"]
    assert "not widened" in record["rejection_outcome"]

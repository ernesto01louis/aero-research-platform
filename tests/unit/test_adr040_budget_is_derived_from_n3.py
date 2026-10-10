"""ADR-040 B1/B2/B3 and the four `GATED_040_*` are DERIVED from the N3 record, never typed.

`test_adr040_marker_state.py` requires this file to exist the moment B1 is filled, and the
reason is the whole point of the three-commit discipline: the sentinels are an OUTPUT of a
measurement, and the only way to keep them honest is a test that recomputes them from the
record and compares. A number that was typed into the module and then "checked" against
itself would pass forever.

**This file was written on 2026-09-14, while N3 was still running and before any of those
numbers existed.** That timing is deliberate and is the property worth preserving: a
derivation test written after the numbers are on the screen can be shaped, however
unconsciously, to the answer it is supposed to check. The rule is tested here against
synthetic confirmations whose arithmetic is known by construction; the second half — the
part that reads the real record — activates by itself the moment
`data/vv/stage20_n3_confirmation.json` lands, and needs no edit then.

What it does NOT do: assert any particular value for the rate, the window count, the
ceiling or the sentinels. Those are measurements, and this test's job is to prove they were
derived, not to agree with them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from aero.vv.fsi.hg2007_sizing import (
    I7Probe,
    N3Confirmation,
    SizingError,
    size_gated_campaign_040,
)

pytestmark = pytest.mark.stage_20

_REPO_ROOT = Path(__file__).resolve().parents[2]
_N3_RECORD = _REPO_ROOT / "data/vv/stage20_n3_confirmation.json"

#: The pre-registered campaign shape these tests size against. Not measurements — the
#: ADR-040 N1/L3 identifiers and ADR-039's S2 analysis rule, all fixed long before N3 ran.
_NUMERICS = "adr040-candidate"
_RANKS = 4
_PERIOD_S = 1.0145
_DISCARD_S = 3.0 * _PERIOD_S


def _probe(arm: str, rung: str, dt: float = 2e-05) -> I7Probe:
    """A COMPLETE I7 probe that clears its Courant bound, so sizing reaches the rate."""
    return I7Probe(
        arm=arm,
        rung=rung,
        dt=dt,
        max_courant_post_ramp=0.42,
        windows_completed=76090,
        windows_requested=76090,
        stopped_by="all-exited",
    )


def _confirmation(arm: str, seconds_per_window: float, dt: float = 2e-05) -> N3Confirmation:
    # A rate read over a fractional quarter-cycle is phase-weighted, and the model refuses
    # it (ADR-040 W3). One quarter-cycle is round(period/4/dt) = 12681 windows here, so the
    # measured span is the largest whole number of them inside 76090 - 50725 = 25365.
    post_ramp = 2 * 12681
    return N3Confirmation(
        arm=arm,
        rung="mid",
        dt=dt,
        period_s=_PERIOD_S,
        numerics_label=_NUMERICS,
        mpi_ranks=_RANKS,
        windows_requested=76090,
        windows_completed=76090,
        stopped_by="all-exited",
        ramp_windows=50725,
        post_ramp_windows_measured=post_ramp,
        post_ramp_wall_clock_s=seconds_per_window * post_ramp,
        max_courant_post_ramp=0.42,
        time_dir_count=200,
        du_bytes=10**10,
        # contention is what makes a rate admissible at all (ADR-040 N3)
        concurrent_with=("the-other-arm",),
    )


def _size(rate_flex: float, rate_rigid: float, ceiling_s: int) -> Any:
    return size_gated_campaign_040(
        probes=[_probe("flexible", "mid"), _probe("rigid", "mid"), _probe("flexible", "fine")],
        confirmations=[
            _confirmation("flexible", rate_flex),
            _confirmation("rigid", rate_rigid),
        ],
        numerics_label=_NUMERICS,
        mpi_ranks=_RANKS,
        discard_s=_DISCARD_S,
        period_s=_PERIOD_S,
        ceiling_s=ceiling_s,
    )


def test_the_projection_tracks_the_measured_rate_rather_than_any_constant() -> None:
    """Double the measured seconds-per-window and the projection doubles.

    This is the property a typed-in number cannot have, and the cheapest way to tell a
    derivation from a transcription.
    """
    slow = _size(4.0, 2.0, ceiling_s=60 * 24 * 3600)
    fast = _size(2.0, 1.0, ceiling_s=60 * 24 * 3600)

    for arm in ("flexible", "rigid"):
        assert slow.projected_wall_s_by_arm[arm] == pytest.approx(
            2.0 * fast.projected_wall_s_by_arm[arm]
        )
    # ...while the campaign SHAPE is a property of the analysis rule, not of the rate
    assert slow.n_windows == fast.n_windows
    assert slow.max_time == fast.max_time
    assert slow.time_window_size == fast.time_window_size


def test_the_window_count_covers_the_discard_plus_the_settled_cycles() -> None:
    """ADR-039 S2 is what sets max_time; N3 only says how long those windows take."""
    sized = _size(3.5, 1.7, ceiling_s=60 * 24 * 3600)
    needed_s = _DISCARD_S + sized.settled_cycles * _PERIOD_S

    assert sized.max_time >= needed_s
    assert sized.n_windows == pytest.approx(sized.max_time / sized.time_window_size, rel=1e-9)
    # and the deck can express it: n*dt must survive CalculiX's .13e field width
    assert float(format(sized.max_time, ".13e")) == sized.max_time


def test_a_ceiling_that_cannot_hold_the_campaign_is_refused_not_trimmed() -> None:
    """B4's order is cut settled cycles, then NO-GO — never silently shrink the campaign."""
    with pytest.raises(SizingError):
        _size(3.5, 1.7, ceiling_s=3600)


def test_the_rate_must_come_from_the_pre_registered_stack() -> None:
    """A rate measured on another stack or rank count is another campaign's rate (L5)."""
    with pytest.raises(SizingError):
        size_gated_campaign_040(
            probes=[_probe("flexible", "mid"), _probe("rigid", "mid"), _probe("flexible", "fine")],
            confirmations=[
                _confirmation("flexible", 3.5).model_copy(
                    update={"numerics_label": "adr039-baseline"}
                ),
                _confirmation("rigid", 1.7),
            ],
            numerics_label=_NUMERICS,
            mpi_ranks=_RANKS,
            discard_s=_DISCARD_S,
            period_s=_PERIOD_S,
            ceiling_s=60 * 24 * 3600,
        )


def test_an_uncontended_confirmation_may_not_size() -> None:
    """ADR-040 N3: a fluid-only screen may not size, and neither may a lone arm."""
    with pytest.raises(SizingError):
        size_gated_campaign_040(
            probes=[_probe("flexible", "mid"), _probe("rigid", "mid"), _probe("flexible", "fine")],
            confirmations=[
                _confirmation("flexible", 3.5).model_copy(update={"concurrent_with": ()}),
                _confirmation("rigid", 1.7),
            ],
            numerics_label=_NUMERICS,
            mpi_ranks=_RANKS,
            discard_s=_DISCARD_S,
            period_s=_PERIOD_S,
            ceiling_s=60 * 24 * 3600,
        )


@pytest.mark.skipif(not _N3_RECORD.exists(), reason="N3 has not been collected yet")
def test_the_filled_sentinels_re_derive_from_the_committed_record() -> None:
    """The live half. It activates by itself when the record lands — no edit needed.

    When `data/vv/stage20_n3_confirmation.json` exists, the four `GATED_040_*` constants
    must be exactly what `size_gated_campaign_040` produces from it. If this fails, the
    sentinels and the record have diverged, and the record is right.
    """
    from aero.vv.fsi.hg2007_flexible_foil import (
        GATED_040_MAX_TIME_S,
        GATED_040_MPI_RANKS,
        GATED_040_NUMERICS_LABEL,
        GATED_040_TIME_WINDOW_S,
    )
    from aero.vv.fsi.hg2007_sizing import i7_probe_from_bundle, n3_confirmation_from_bundle

    record = json.loads(_N3_RECORD.read_text(encoding="utf-8"))
    bundles = record["bundles"] if "bundles" in record else record["arms"]

    probes = [i7_probe_from_bundle(b) for b in bundles.values() if "i7" in b]
    confirmations = [n3_confirmation_from_bundle(b) for b in bundles.values() if "n3" in b]
    sized = size_gated_campaign_040(
        probes=probes,
        confirmations=confirmations,
        numerics_label=record["numerics_label"],
        mpi_ranks=record["mpi_ranks"],
        discard_s=record["discard_s"],
        period_s=record["period_s"],
        ceiling_s=record["ceiling_s"],
    )

    assert sized.time_window_size == GATED_040_TIME_WINDOW_S
    assert sized.max_time == GATED_040_MAX_TIME_S
    assert record["numerics_label"] == GATED_040_NUMERICS_LABEL
    assert record["mpi_ranks"] == GATED_040_MPI_RANKS

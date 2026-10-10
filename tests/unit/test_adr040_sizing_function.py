"""ADR-040's sizing rule refuses, loudly, for reasons the ADR-039 rule could not have.

The ADR-039 sizing test covers the shared machinery (dt round trip, fine-rung Courant,
contention, the ceiling refusal) and is untouched. This file covers only what ADR-040
changed, which is the definition of the RATE, plus the two identity checks the new gated
predicate implies:

* a rate read from inside the ramp may never size — the failure that would otherwise
  produce a comfortable number and an unaffordable campaign;
* a rate measured on the wrong linear-solver stack, or at the wrong rank count, is another
  campaign's rate;
* a ceiling stop is admissible *if and only if* it cleared the ramp with whole
  quarter-cycles behind it (ADR-040 W3), which is the one place ADR-040 is deliberately
  more permissive than ADR-039.

The numbers are the campaign's real ones: dt = 2e-5 s, T = 1.0145 s, a 50 725-window ramp.
"""

from __future__ import annotations

import math

import pytest
from aero.vv.fsi.hg2007_sizing import (
    I7Probe,
    N3Confirmation,
    SizingError,
    size_gated_campaign_040,
)

pytestmark = pytest.mark.stage_20

_DT = 2.0e-5
_PERIOD = 1.0145
_DISCARD = 3.0 * _PERIOD
_RAMP_WINDOWS = 50725
_QUARTER_WINDOWS = 12681  # one post-ramp quarter-cycle, to the nearest window
_CEILING_S = 30 * 24 * 3600
_LABEL = "adr040-candidate"
_RANKS = 4


def _probe(**over: object) -> I7Probe:
    base: dict[str, object] = {
        "arm": "flexible",
        "rung": "mid",
        "dt": _DT,
        "max_courant_post_ramp": 0.55,
        "windows_requested": 76090,
        "windows_completed": 76090,
        "stopped_by": "all-exited",
    }
    return I7Probe.model_validate(base | over)


def _confirmation(**over: object) -> N3Confirmation:
    base: dict[str, object] = {
        "arm": "flexible",
        "rung": "mid",
        "dt": _DT,
        "period_s": _PERIOD,
        "numerics_label": _LABEL,
        "mpi_ranks": _RANKS,
        "windows_requested": 76090,
        "windows_completed": 76090,
        "stopped_by": "all-exited",
        "ramp_windows": _RAMP_WINDOWS,
        "post_ramp_windows_measured": 2 * _QUARTER_WINDOWS,
        "post_ramp_wall_clock_s": 2 * _QUARTER_WINDOWS * 1.5,
        "time_dir_count": 497,
        "du_bytes": 342_749_623,
        "concurrent_with": ("hg2007_rigid_foil-x",),
    }
    return N3Confirmation.model_validate(base | over)


def _record() -> tuple[list[I7Probe], list[N3Confirmation]]:
    probes = [
        _probe(),
        _probe(arm="rigid"),
        _probe(rung="fine", max_courant_post_ramp=0.72),
    ]
    confirmations = [
        _confirmation(),
        _confirmation(arm="rigid", concurrent_with=("hg2007_flexible_foil-x",)),
    ]
    return probes, confirmations


def _size(**over: object) -> object:
    probes, confirmations = _record()
    kwargs: dict[str, object] = {
        "probes": probes,
        "confirmations": confirmations,
        "numerics_label": _LABEL,
        "mpi_ranks": _RANKS,
        "discard_s": _DISCARD,
        "period_s": _PERIOD,
        "ceiling_s": _CEILING_S,
    }
    return size_gated_campaign_040(**(kwargs | over))  # type: ignore[arg-type]


def test_the_happy_path_sizes_from_the_post_ramp_rate() -> None:
    sized = _size()
    expected_n = math.ceil((_DISCARD + 20.0 * _PERIOD) / _DT)
    assert sized.time_window_size == _DT  # type: ignore[attr-defined]
    assert sized.n_windows >= expected_n  # type: ignore[attr-defined]
    assert sized.max_time == sized.n_windows * _DT  # type: ignore[attr-defined]
    assert float(format(sized.max_time, ".13e")) == sized.max_time  # type: ignore[attr-defined]
    # 1.5 s/window exactly — the POST-RAMP rate, not 76090 windows' worth of average.
    assert sized.projected_wall_s_by_arm["flexible"] == sized.n_windows * 1.5  # type: ignore[attr-defined]


def test_the_rate_is_not_the_whole_run_average() -> None:
    """The defect this function exists to prevent, stated as an inequality.

    Two thirds of N3's windows are ramp windows at near-zero plunge. If the rule averaged
    the whole run it would report a rate a long way below the post-ramp one and size a
    campaign that cannot be afforded.
    """
    confirmation = _confirmation(
        post_ramp_windows_measured=2 * _QUARTER_WINDOWS,
        post_ramp_wall_clock_s=2 * _QUARTER_WINDOWS * 1.5,
    )
    whole_run_average = 30000.0 / confirmation.windows_completed
    assert confirmation.post_ramp_seconds_per_window == pytest.approx(1.5)
    assert whole_run_average < 0.5, "the fixture no longer demonstrates the gap"


def test_a_run_that_never_cleared_the_ramp_may_not_size() -> None:
    probes, _ = _record()
    inside_ramp = [
        _confirmation(
            windows_completed=40000,
            stopped_by="ceiling",
            post_ramp_windows_measured=0,
            post_ramp_wall_clock_s=0.0,
        ),
        _confirmation(
            arm="rigid",
            windows_completed=40000,
            stopped_by="ceiling",
            post_ramp_windows_measured=0,
            post_ramp_wall_clock_s=0.0,
            concurrent_with=("hg2007_flexible_foil-x",),
        ),
    ]
    assert inside_ramp[0].post_ramp_seconds_per_window is None
    with pytest.raises(SizingError, match="ramp-phase rate may not size"):
        _size(probes=probes, confirmations=inside_ramp)


def test_a_ceiling_stop_past_the_ramp_does_size() -> None:
    """ADR-040 W3, the one place this rule is deliberately laxer than ADR-039's."""
    probes, _ = _record()
    stopped = [
        _confirmation(
            windows_completed=_RAMP_WINDOWS + _QUARTER_WINDOWS,
            stopped_by="ceiling",
            post_ramp_windows_measured=_QUARTER_WINDOWS,
            post_ramp_wall_clock_s=_QUARTER_WINDOWS * 1.5,
        ),
        _confirmation(
            arm="rigid",
            windows_completed=_RAMP_WINDOWS + _QUARTER_WINDOWS,
            stopped_by="ceiling",
            post_ramp_windows_measured=_QUARTER_WINDOWS,
            post_ramp_wall_clock_s=_QUARTER_WINDOWS * 1.5,
            concurrent_with=("hg2007_flexible_foil-x",),
        ),
    ]
    assert stopped[0].post_ramp_quarter_cycles == 1
    sized = _size(probes=probes, confirmations=stopped)
    assert sized.projected_wall_s_by_arm["rigid"] == sized.n_windows * 1.5  # type: ignore[attr-defined]


def test_a_participant_death_may_not_size_at_any_length() -> None:
    died = _confirmation(stopped_by="participant-died")
    assert died.post_ramp_seconds_per_window is None


def test_a_fractional_quarter_cycle_span_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="not a whole number of them"):
        _confirmation(post_ramp_windows_measured=_QUARTER_WINDOWS + 3000)


def test_the_wrong_numerics_stack_is_another_campaigns_rate() -> None:
    probes, _ = _record()
    baseline = [
        _confirmation(numerics_label="adr039-baseline"),
        _confirmation(
            arm="rigid",
            numerics_label="adr039-baseline",
            concurrent_with=("hg2007_flexible_foil-x",),
        ),
    ]
    with pytest.raises(SizingError, match="not at the pre-registered"):
        _size(probes=probes, confirmations=baseline)


def test_the_wrong_rank_count_is_another_campaigns_rate() -> None:
    probes, _ = _record()
    six = [
        _confirmation(mpi_ranks=6),
        _confirmation(arm="rigid", mpi_ranks=6, concurrent_with=("hg2007_flexible_foil-x",)),
    ]
    with pytest.raises(SizingError, match="not at the pre-registered"):
        _size(probes=probes, confirmations=six)


def test_an_uncontended_confirmation_is_refused() -> None:
    probes, _ = _record()
    alone = [_confirmation(concurrent_with=()), _confirmation(arm="rigid", concurrent_with=())]
    with pytest.raises(SizingError, match="measured alone"):
        _size(probes=probes, confirmations=alone)


def test_a_projection_over_the_ceiling_is_a_budget_no_go() -> None:
    with pytest.raises(SizingError, match="NO-GO"):
        _size(ceiling_s=14 * 24 * 3600)


def test_the_ceiling_has_no_default() -> None:
    """ADR-039's 14-day default is measured out of reach; a default here would be a
    ceiling nobody chose (ADR-040 B3)."""
    probes, confirmations = _record()
    with pytest.raises(TypeError, match="ceiling_s"):
        size_gated_campaign_040(  # type: ignore[call-arg]
            probes=probes,
            confirmations=confirmations,
            numerics_label=_LABEL,
            mpi_ranks=_RANKS,
            discard_s=_DISCARD,
            period_s=_PERIOD,
        )


def test_a_failing_fine_rung_courant_probe_still_refuses() -> None:
    """ADR-039's machinery, carried over unchanged (U3) — asserted, not assumed."""
    probes = [_probe(), _probe(arm="rigid"), _probe(rung="fine", max_courant_post_ramp=1.31)]
    with pytest.raises(SizingError, match="never adjusts"):
        _size(probes=probes)

"""The B2 sizing rule is pure, refuses transients, and never rescales a failed probe.

CI-enforced (``tests/unit``): the rule is pre-registered in ADR-039 while B2 carries the
``<<B2-PENDING-I4>>`` marker, so the function's refusal behaviour IS part of the
pre-registration — a rule that quietly sized a campaign from a transient or a rescaled
Courant number would defeat the marker's whole point.
"""

from __future__ import annotations

import math

import pytest
from aero.vv.fsi.hg2007_sizing import (
    I4Calibration,
    I7Probe,
    SizingError,
    size_gated_campaign,
    suggest_next_dt,
)

pytestmark = pytest.mark.stage_20

_DT = 3.5e-4
_PERIOD = 1.0145
_DISCARD = 3.0 * _PERIOD


def _probe(**overrides: object) -> I7Probe:
    values: dict[str, object] = {
        "arm": "flexible",
        "rung": "mid",
        "dt": _DT,
        "max_courant_post_ramp": 0.42,
        "windows_requested": 4350,
        "windows_completed": 4350,
        "stopped_by": "all-exited",
    }
    values.update(overrides)
    return I7Probe(**values)  # type: ignore[arg-type]


def _calibration(**overrides: object) -> I4Calibration:
    values: dict[str, object] = {
        "arm": "flexible",
        "rung": "mid",
        "dt": _DT,
        "windows_requested": 4350,
        "windows_completed": 4350,
        "stopped_by": "all-exited",
        "wall_clock_s": 8700.0,
        "iterations_per_window_mean": 2.4,
        "time_dir_count": 4351,
        "du_bytes": 2_000_000_000,
        "concurrent_with": ("hg2007_rigid_foil-20260810-000000",),
    }
    values.update(overrides)
    return I4Calibration(**values)  # type: ignore[arg-type]


def _full_record() -> tuple[list[I7Probe], list[I4Calibration]]:
    probes = [
        _probe(),
        _probe(arm="rigid"),
        _probe(rung="fine", max_courant_post_ramp=0.55),
    ]
    calibrations = [
        _calibration(),
        _calibration(arm="rigid", wall_clock_s=7830.0, concurrent_with=("hg2007_flexible_foil-x",)),
    ]
    return probes, calibrations


def _size(**overrides: object):  # type: ignore[no-untyped-def]
    probes, calibrations = _full_record()
    kwargs: dict[str, object] = {
        "probes": probes,
        "calibrations": calibrations,
        "discard_s": _DISCARD,
        "period_s": _PERIOD,
    }
    kwargs.update(overrides)
    return size_gated_campaign(**kwargs)  # type: ignore[arg-type]


def test_the_happy_path_sizes_from_the_record() -> None:
    sized = _size()
    assert sized.time_window_size == _DT
    expected_n = math.ceil((_DISCARD + 20.0 * _PERIOD) / _DT)
    assert sized.n_windows >= expected_n
    assert sized.max_time == sized.n_windows * _DT
    assert float(format(sized.max_time, ".13e")) == sized.max_time
    assert sized.projected_wall_s_by_arm["flexible"] == sized.n_windows * (8700.0 / 4350)


def test_a_transient_probe_is_refused() -> None:
    probes, calibrations = _full_record()
    probes[0] = _probe(windows_completed=312)
    with pytest.raises(SizingError, match="transient"):
        size_gated_campaign(
            probes=probes, calibrations=calibrations, discard_s=_DISCARD, period_s=_PERIOD
        )


def test_a_killed_calibration_is_refused() -> None:
    probes, calibrations = _full_record()
    calibrations[0] = _calibration(stopped_by="ceiling")
    with pytest.raises(SizingError, match="all-exited"):
        size_gated_campaign(
            probes=probes, calibrations=calibrations, discard_s=_DISCARD, period_s=_PERIOD
        )


def test_a_failed_courant_probe_is_refused_not_rescaled() -> None:
    probes, calibrations = _full_record()
    probes[2] = _probe(rung="fine", max_courant_post_ramp=1.31)
    with pytest.raises(SizingError, match="never adjusts"):
        size_gated_campaign(
            probes=probes, calibrations=calibrations, discard_s=_DISCARD, period_s=_PERIOD
        )


def test_a_missing_fine_rung_probe_is_refused() -> None:
    probes, calibrations = _full_record()
    with pytest.raises(SizingError, match="fine"):
        size_gated_campaign(
            probes=probes[:2], calibrations=calibrations, discard_s=_DISCARD, period_s=_PERIOD
        )


def test_probes_at_two_dts_are_refused() -> None:
    probes, calibrations = _full_record()
    probes[1] = _probe(arm="rigid", dt=2.0e-4)
    with pytest.raises(SizingError, match="disagree on dt"):
        size_gated_campaign(
            probes=probes, calibrations=calibrations, discard_s=_DISCARD, period_s=_PERIOD
        )


def test_an_uncontended_gated_rung_calibration_is_refused() -> None:
    probes, calibrations = _full_record()
    calibrations[0] = _calibration(concurrent_with=())
    with pytest.raises(SizingError, match=r"contention|concurrently"):
        size_gated_campaign(
            probes=probes, calibrations=calibrations, discard_s=_DISCARD, period_s=_PERIOD
        )


def test_a_campaign_past_the_ceiling_is_a_budget_refusal() -> None:
    probes, calibrations = _full_record()
    calibrations[0] = _calibration(wall_clock_s=4350.0 * 25.0)
    with pytest.raises(SizingError, match="NO-GO"):
        size_gated_campaign(
            probes=probes, calibrations=calibrations, discard_s=_DISCARD, period_s=_PERIOD
        )


def test_a_non_representable_dt_is_refused() -> None:
    probes = [
        _probe(dt=math.pi * 1.0e-4),
        _probe(arm="rigid", dt=math.pi * 1.0e-4),
        _probe(rung="fine", dt=math.pi * 1.0e-4),
    ]
    _, calibrations = _full_record()
    with pytest.raises(SizingError, match="round trip"):
        size_gated_campaign(
            probes=probes, calibrations=calibrations, discard_s=_DISCARD, period_s=_PERIOD
        )


def test_suggest_next_dt_refuses_a_passing_probe_and_cleans_a_failing_one() -> None:
    with pytest.raises(SizingError, match="verbatim"):
        suggest_next_dt(_probe())
    suggestion = suggest_next_dt(_probe(max_courant_post_ramp=2.6))
    assert suggestion < _DT * 0.8 / 2.6 * 1.0000001
    assert float(format(suggestion, ".13e")) == suggestion

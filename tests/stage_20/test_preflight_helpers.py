"""The reusable pre-flight helpers: per-signal S5 and the I8 comparison half."""

from __future__ import annotations

import pytest
from aero.vv.fsi.preflight import (
    PreflightError,
    compare_window_traces,
    signal_drift_reports,
)

from tests.stage_20._settling import _fixture

pytestmark = pytest.mark.stage_20


def test_per_signal_drift_reports_cover_the_named_signals() -> None:
    _, _, analysis = _fixture()
    reports = signal_drift_reports(analysis, signals=("c_t", "c_p"))
    assert [r.signal for r in reports] == ["c_t", "c_p"]
    for report in reports:
        assert report.n_tail_cycles >= 2
        assert report.passed  # the fixture settles within a cycle by construction


def test_a_missing_signal_is_refused_not_skipped() -> None:
    _, _, analysis = _fixture()
    with pytest.raises(PreflightError, match="missing series would silently pass"):
        signal_drift_reports(analysis, signals=("c_t", "no_such_signal"))


def test_a_drifting_signal_fails_its_own_report() -> None:
    _, _, analysis = _fixture()
    (report,) = signal_drift_reports(analysis, signals=("c_t",), tol=1.0e-9)
    assert not report.passed  # noise alone exceeds a 1e-9 bound; the tol is honoured


def test_window_trace_comparison_is_bitwise_aware() -> None:
    t = (0.001, 0.002, 0.003)
    same = compare_window_traces(t, (1.0, 2.0, 3.0), t, (1.0, 2.0, 3.0))
    assert same.bitwise_identical and same.max_abs_difference == 0.0
    off = compare_window_traces(t, (1.0, 2.0, 3.0), t, (1.0, 2.0, 3.5))
    assert not off.bitwise_identical
    assert off.max_abs_difference == 0.5 and off.where == 2


def test_mismatched_schedules_are_refused() -> None:
    with pytest.raises(PreflightError, match="schedules differ"):
        compare_window_traces((0.001, 0.002), (1.0, 2.0), (0.001, 0.003), (1.0, 2.0))
    with pytest.raises(PreflightError, match="SAME windows"):
        compare_window_traces((0.001,), (1.0,), (0.001, 0.002), (1.0, 2.0))


def test_numpy_is_not_fooled_by_negative_zero() -> None:
    t = (0.001,)
    comparison = compare_window_traces(t, (0.0,), t, (-0.0,))
    assert comparison.bitwise_identical  # == on floats; -0.0 == 0.0 is the right answer

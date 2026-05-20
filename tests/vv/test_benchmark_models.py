"""Stage 05 unit tests for the V&V harness data models and comparison logic."""

from __future__ import annotations

import pytest
from aero.vv import (
    BenchmarkError,
    MetricSpec,
    ReferenceData,
    Series,
    compare,
)

pytestmark = pytest.mark.stage_05


# --- Series -------------------------------------------------------------------
def test_series_rejects_mismatched_lengths() -> None:
    with pytest.raises(Exception, match="length"):
        Series(x=(0.0, 1.0, 2.0), y=(0.0, 1.0))


def test_series_rejects_single_sample() -> None:
    with pytest.raises(Exception, match="at least two"):
        Series(x=(0.0,), y=(0.0,))


def test_series_is_frozen() -> None:
    s = Series(x=(0.0, 1.0), y=(0.0, 1.0))
    with pytest.raises(Exception):  # noqa: B017 — frozen
        s.x = (1.0, 2.0)  # type: ignore[misc]


# --- scalar comparison --------------------------------------------------------
def test_scalar_metric_passes_within_tolerance() -> None:
    metric = MetricSpec(name="cd", kind="scalar", tolerance=0.03)
    ref = ReferenceData(case_name="naca0012", source="NASA TMR", scalars={"cd": 0.0080})
    result = compare(metric, 0.00818, ref)  # +2.25%
    assert result.passed
    assert result.error == pytest.approx(0.0225, abs=1e-3)
    assert result.measured == 0.00818
    assert result.reference == 0.0080


def test_scalar_metric_fails_outside_tolerance() -> None:
    metric = MetricSpec(name="cd", kind="scalar", tolerance=0.03)
    ref = ReferenceData(case_name="naca0012", source="NASA TMR", scalars={"cd": 0.0080})
    result = compare(metric, 0.0090, ref)  # +12.5%
    assert not result.passed


def test_scalar_metric_without_reference_fails_loud() -> None:
    metric = MetricSpec(name="cd", kind="scalar", tolerance=0.03)
    ref = ReferenceData(case_name="naca0012", source="NASA TMR")
    with pytest.raises(BenchmarkError, match="no scalar reference"):
        compare(metric, 0.008, ref)


# --- pointwise comparison -----------------------------------------------------
def test_pointwise_relative_comparison_interpolates_onto_reference() -> None:
    # Measured Cf sampled densely; reference at coarser x. A uniform +4% bias.
    mx = tuple(i / 100.0 for i in range(101))
    measured = Series(x=mx, y=tuple(0.003 * 1.04 for _ in mx))
    ref = ReferenceData(
        case_name="flat_plate",
        source="NASA TMR",
        series={"cf": Series(x=(0.1, 0.5, 0.9), y=(0.003, 0.003, 0.003))},
    )
    metric = MetricSpec(name="cf", kind="pointwise", tolerance=0.05, comparison="relative")
    result = compare(metric, measured, ref)
    assert result.error == pytest.approx(0.04, abs=2e-3)
    assert result.passed


def test_pointwise_normalized_comparison_handles_sign_change() -> None:
    # Cp crosses zero — `normalized` divides by the peak magnitude, not per point.
    mx = tuple(i / 10.0 for i in range(11))
    measured = Series(x=mx, y=tuple(1.0 - 2.0 * x for x in mx))  # +1 .. -1
    ref = ReferenceData(
        case_name="bump_2d",
        source="NASA TMR",
        series={"cp": Series(x=(0.2, 0.5, 0.8), y=(0.6, 0.0, -0.6))},
    )
    metric = MetricSpec(name="cp", kind="pointwise", tolerance=0.03, comparison="normalized")
    result = compare(metric, measured, ref)
    assert result.passed  # measured equals reference exactly here
    assert result.error == pytest.approx(0.0, abs=1e-6)


def test_pointwise_requires_overlapping_x_range() -> None:
    measured = Series(x=(0.0, 0.1, 0.2), y=(1.0, 1.0, 1.0))
    ref = ReferenceData(
        case_name="c",
        source="s",
        series={"cf": Series(x=(5.0, 6.0), y=(1.0, 1.0))},  # disjoint
    )
    metric = MetricSpec(name="cf", kind="pointwise", tolerance=0.05)
    with pytest.raises(BenchmarkError, match="overlaps fewer than 2"):
        compare(metric, measured, ref)


def test_metric_spec_rejects_unknown_field() -> None:
    with pytest.raises(Exception):  # noqa: B017 — extra='forbid'
        MetricSpec(name="cd", kind="scalar", tolerance=0.03, bogus=1)  # type: ignore[call-arg]

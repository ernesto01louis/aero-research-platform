"""Two arms are comparable, or they are refused — with the arithmetic that shows why.

A matched-condition delta only cancels correlated error if the runs really are matched.
By the time `paired_delta_uncertainty` sees them, both records are already per-cycle means,
so the ways they drift apart are invisible: a dropped sample, a detected rather than
prescribed period, a different discard. Each is checked here against a deliberately
mismatched pair.

The efficiency helpers are here too, because `eta` is the one gated quantity that is a
RATIO and the ratio-of-means / mean-of-ratios distinction has to be pinned somewhere a
future reader will find it.
"""

from __future__ import annotations

import numpy as np
import pytest
from aero.postprocess.limit_cycle import analyse_limit_cycle
from aero.vv.alignment import (
    AlignedPair,
    AlignmentError,
    align_arms,
    assert_common_time_base,
    per_cycle_efficiency,
    window_efficiency,
)

pytestmark = pytest.mark.stage_20

PERIOD = 1.0145


def _arm(*, offset: float = 0.4, transient_cycles: float = 1.0, seed: int = 0, cycles: int = 24):
    t = np.linspace(0.0, cycles * PERIOD, cycles * 400, endpoint=False)
    rng = np.random.default_rng(seed)
    decay = 0.3 * np.exp(-t / (transient_cycles * PERIOD))
    jitter = rng.normal(0.0, 0.01 * max(abs(offset), 0.1), size=t.size)
    signals = {
        "thrust": offset + decay + np.cos(2.0 * np.pi * t / PERIOD) + jitter,
        "power": 2.0 * offset + decay + np.sin(2.0 * np.pi * t / PERIOD) + jitter,
    }
    return t, signals


def _analysis(t, signals, **kwargs):
    return analyse_limit_cycle(t, signals, fundamental="thrust", period=PERIOD, **kwargs)


class TestTheTimeBaseMustBeShared:
    def test_identical_schedules_align(self) -> None:
        t_a, _ = _arm(seed=1)
        t_b, _ = _arm(seed=2)
        assert_common_time_base(t_a, t_b)  # same prescribed schedule -> same doubles

    def test_a_dropped_sample_is_refused(self) -> None:
        # Exactly what force_io's de-duplication does when timePrecision is too coarse.
        t_a, _ = _arm()
        t_b = np.delete(t_a, 500)
        with pytest.raises(AlignmentError, match="different sample counts"):
            assert_common_time_base(t_a, t_b)

    def test_a_shifted_instant_is_refused_with_its_index(self) -> None:
        t_a, _ = _arm()
        t_b = t_a.copy()
        t_b[700] = np.nextafter(t_b[700], 1.0)  # one ULP -- the smallest possible drift
        with pytest.raises(AlignmentError, match="index 700"):
            assert_common_time_base(t_a, t_b)

    def test_bitwise_is_the_right_test_here(self) -> None:
        # Not across an ASCII round trip between independent accumulators, but between two
        # runs of ONE writer on ONE prescribed schedule -- where equality is achievable.
        t_a, _ = _arm(seed=1)
        t_b, _ = _arm(seed=9)
        assert np.array_equal(t_a, t_b)


class TestAlignArms:
    def test_two_matched_arms_report_the_later_anchor(self) -> None:
        t_a, sig_a = _arm(offset=0.40, transient_cycles=0.8, seed=1)
        t_b, sig_b = _arm(offset=0.55, transient_cycles=1.6, seed=2)
        a, b = _analysis(t_a, sig_a), _analysis(t_b, sig_b)
        pair = align_arms(a, b, baseline_t=t_a, candidate_t=t_b)

        assert pair.baseline_anchor != pair.candidate_anchor
        assert pair.pair_start == max(pair.baseline_anchor, pair.candidate_anchor)
        assert pair.n_pairs >= 4
        assert pair.period == PERIOD

    def test_a_detected_period_is_refused(self) -> None:
        # The default path is fine on its own; it is unusable for a PAIRED claim.
        t_a, sig_a = _arm(seed=1)
        t_b, sig_b = _arm(seed=2)
        detected = analyse_limit_cycle(t_a, sig_a, fundamental="thrust")
        prescribed = _analysis(t_b, sig_b)
        with pytest.raises(AlignmentError, match="prescribed period"):
            align_arms(detected, prescribed)

    def test_different_prescribed_periods_are_refused(self) -> None:
        t_a, sig_a = _arm(seed=1)
        t_b, sig_b = _arm(seed=2)
        a = _analysis(t_a, sig_a)
        b = analyse_limit_cycle(t_b, sig_b, fundamental="thrust", period=PERIOD * 1.001)
        with pytest.raises(AlignmentError, match="different periods"):
            align_arms(a, b)

    def test_different_discards_are_refused(self) -> None:
        t_a, sig_a = _arm(seed=1)
        t_b, sig_b = _arm(seed=2)
        a = _analysis(t_a, sig_a, discard_s=0.0)
        b = _analysis(t_b, sig_b, discard_s=PERIOD)
        with pytest.raises(AlignmentError, match="different start-up windows"):
            align_arms(a, b)

    def test_a_mismatched_time_base_is_refused_through_align(self) -> None:
        t_a, sig_a = _arm(seed=1)
        t_b, sig_b = _arm(seed=2)
        a, b = _analysis(t_a, sig_a), _analysis(t_b, sig_b)
        with pytest.raises(AlignmentError, match="different sample counts"):
            align_arms(a, b, baseline_t=t_a, candidate_t=t_b[:-1])


class TestTheEvidenceObjectCannotOverstateWhatWasChecked:
    """An `AlignedPair` is the evidence that two arms are comparable.

    Found by adversarial review of session 5, before the first caller existed. The bitwise
    raw-time comparison was conditional on BOTH arrays being supplied, while `n_samples` was
    derived from `baseline_t` alone -- so `align_arms(a, b, baseline_t=t)` returned an object
    bitwise identical to a fully checked one while never having compared a single instant,
    and the no-times call recorded a fabricated `n_samples = 2` that clears its own `ge=2`
    floor and reads like a measurement.
    """

    def test_a_one_sided_call_is_refused_rather_than_silently_unchecked(self) -> None:
        t_a, sig_a = _arm(seed=1)
        t_b, sig_b = _arm(seed=2)
        a, b = _analysis(t_a, sig_a), _analysis(t_b, sig_b)
        for kwargs in ({"baseline_t": t_a}, {"candidate_t": t_b}):
            with pytest.raises(AlignmentError, match="Pass both or neither"):
                align_arms(a, b, **kwargs)

    def test_the_one_sided_call_would_have_hidden_a_real_mismatch(self) -> None:
        """The exact scenario: a shifted candidate that the two-sided call refuses loudly."""
        t_a, sig_a = _arm(seed=1)
        t_b, sig_b = _arm(seed=2)
        a, b = _analysis(t_a, sig_a), _analysis(t_b, sig_b)
        shifted = t_b + (t_b[1] - t_b[0])
        with pytest.raises(AlignmentError, match="same instants"):
            align_arms(a, b, baseline_t=t_a, candidate_t=shifted)
        # ...and the one-sided form that used to accept it now cannot be spelled at all.
        with pytest.raises(AlignmentError, match="Pass both or neither"):
            align_arms(a, b, baseline_t=t_a)

    def test_no_raw_times_means_an_absent_count_not_a_fabricated_one(self) -> None:
        t_a, sig_a = _arm(offset=0.40, transient_cycles=0.8, seed=1)
        t_b, sig_b = _arm(offset=0.55, transient_cycles=1.6, seed=2)
        pair = align_arms(_analysis(t_a, sig_a), _analysis(t_b, sig_b))
        assert pair.n_samples is None
        assert pair.time_base_checked is False

    def test_a_checked_pair_says_so(self) -> None:
        t_a, sig_a = _arm(offset=0.40, transient_cycles=0.8, seed=1)
        t_b, sig_b = _arm(offset=0.55, transient_cycles=1.6, seed=2)
        pair = align_arms(
            _analysis(t_a, sig_a), _analysis(t_b, sig_b), baseline_t=t_a, candidate_t=t_b
        )
        assert pair.time_base_checked is True
        assert pair.n_samples == t_a.size

    def test_a_sample_count_without_a_check_cannot_be_constructed(self) -> None:
        """The two fields are bound, so a hand-built AlignedPair cannot claim more than it did."""
        from pydantic import ValidationError

        common = {
            "period": PERIOD,
            "pair_start": 2,
            "n_pairs": 8,
            "baseline_anchor": 1,
            "candidate_anchor": 2,
            "post_discard_origin": 0.0,
        }
        with pytest.raises(ValidationError, match="disagree"):
            AlignedPair(**common, time_base_checked=False, n_samples=9600)
        with pytest.raises(ValidationError, match="disagree"):
            AlignedPair(**common, time_base_checked=True, n_samples=None)


class TestTheSegmentationAnchorsAreCheckedWithoutRawTimes:
    """The RESUME's third clause, and the one that was missing entirely.

    Equal `discard_s` does NOT imply equal origins: the origin is the first SAMPLE at or
    after the discard, so one dropped row moves it by a time step. The check needs no raw
    times -- `t_start - converged_from_cycle * period` recovers the origin from fields both
    analyses already carry -- so it is unconditional.
    """

    def test_matched_arms_share_an_origin(self) -> None:
        t_a, sig_a = _arm(offset=0.40, transient_cycles=0.8, seed=1)
        t_b, sig_b = _arm(offset=0.55, transient_cycles=1.6, seed=2)
        pair = align_arms(_analysis(t_a, sig_a), _analysis(t_b, sig_b))
        assert pair.post_discard_origin == pytest.approx(0.0, abs=1e-9 * PERIOD)

    def test_a_shifted_origin_is_refused_with_no_raw_times_at_all(self) -> None:
        t_a, sig_a = _arm(offset=0.40, transient_cycles=0.8, seed=1)
        t_b, sig_b = _arm(offset=0.55, transient_cycles=1.6, seed=2)
        # One arm's record starts one time step later -- what a dropped leading row does.
        dt = t_b[1] - t_b[0]
        a = _analysis(t_a, sig_a)
        b = _analysis(t_b + dt, sig_b)
        with pytest.raises(AlignmentError, match="different origins"):
            align_arms(a, b)


class TestEfficiencyIsARatioOfMeans:
    def test_each_cycle_is_its_own_ratio(self) -> None:
        thrust = np.array([1.0, 2.0, 3.0])
        power = np.array([2.0, 8.0, 6.0])
        assert np.allclose(per_cycle_efficiency(thrust, power), [0.5, 0.25, 0.5])

    def test_the_window_value_is_not_the_mean_of_the_per_cycle_ratios(self) -> None:
        """The headline distinction, made falsifiable.

        `eta` is defined on cycle-mean thrust over cycle-mean power. Averaging the
        per-cycle ratios instead is a different number whenever the power varies, and it
        has no physical definition -- it weights cycles by the inverse of their own power.
        """
        thrust = np.array([1.0, 2.0, 3.0])
        power = np.array([2.0, 8.0, 6.0])

        ratio_of_means = window_efficiency(thrust, power)
        mean_of_ratios = float(np.mean(per_cycle_efficiency(thrust, power)))

        assert ratio_of_means == pytest.approx(6.0 / 16.0)  # 0.375
        assert mean_of_ratios == pytest.approx(1.0 / 3.0 + 1.0 / 12.0)  # ~0.4167
        assert ratio_of_means != pytest.approx(mean_of_ratios)

    def test_they_agree_only_when_the_power_is_constant(self) -> None:
        thrust = np.array([1.0, 2.0, 3.0])
        power = np.full(3, 4.0)
        assert window_efficiency(thrust, power) == pytest.approx(
            float(np.mean(per_cycle_efficiency(thrust, power)))
        )

    def test_a_zero_power_cycle_is_refused_rather_than_infinite(self) -> None:
        with pytest.raises(AlignmentError, match="undefined"):
            per_cycle_efficiency(np.array([1.0, 1.0]), np.array([2.0, 0.0]))

    def test_mismatched_lengths_are_refused(self) -> None:
        with pytest.raises(AlignmentError, match="different cycle counts"):
            per_cycle_efficiency(np.array([1.0, 2.0]), np.array([1.0]))

    def test_the_per_cycle_series_is_what_the_paired_path_differences(self) -> None:
        # D2/D4 gate efficiency, so the paired estimator needs a per-cycle eta series;
        # before this helper there was none, only a single collapsed number.
        t_a, sig_a = _arm(offset=0.40, seed=1)
        t_b, sig_b = _arm(offset=0.55, seed=2)
        a, b = _analysis(t_a, sig_a), _analysis(t_b, sig_b)
        pair = align_arms(a, b, baseline_t=t_a, candidate_t=t_b)

        eta_a = per_cycle_efficiency(
            np.asarray(a.cycles_of("thrust").per_cycle_mean),
            np.asarray(a.cycles_of("power").per_cycle_mean),
        )
        eta_b = per_cycle_efficiency(
            np.asarray(b.cycles_of("thrust").per_cycle_mean),
            np.asarray(b.cycles_of("power").per_cycle_mean),
        )
        window = slice(pair.pair_start, pair.pair_start + pair.n_pairs)
        assert eta_a[window].size == pair.n_pairs
        assert eta_b[window].size == pair.n_pairs

"""`analyse_limit_cycle` keeps what the paired path needs, and can segment on a PRESCRIBED period.

Two additions, both forced by the Stage-20 flexible-vs-rigid increment.

**The per-cycle objects were discarded.** `paired_delta_uncertainty` takes exactly two
things per arm -- a `CycleSamples` and a `CycleConvergenceReport` -- and the analysis
computed both and threw them away, keeping only collapsed means. The statistics cannot
reconstruct them, so the paired path could not be called at all.

**The period must be prescribed, not detected.** `paired_delta_uncertainty` compares the
two arms' periods at `rtol = 1e-9`. Two independently FFT-detected periods never agree to
nine digits, so it would refuse the comparison -- correctly, because segmenting two
records at slightly different periods puts their cycle boundaries on a slow relative drift
and the per-cycle difference series then measures that drift instead of the physics.

The default path is untouched: with no period given, the detected one is used and
`fundamental_frequency` is what it always was.
"""

from __future__ import annotations

import numpy as np
import pytest
from aero.postprocess.cycle_detection import CycleConvergenceReport
from aero.postprocess.limit_cycle import LimitCycleError, analyse_limit_cycle
from aero.postprocess.phase_averaging import CycleSamples
from aero.vv.paired_difference import paired_delta_uncertainty

pytestmark = pytest.mark.stage_20

PERIOD = 1.0145
FREQUENCY = 1.0 / PERIOD


def _record(
    *,
    amplitude: float = 1.0,
    offset: float = 0.0,
    cycles: int = 24,
    period: float = PERIOD,
    seed: int = 0,
):
    """A limit cycle with realistic cycle-to-cycle jitter: 400 samples per cycle, no drift.

    The jitter is not decoration. A perfectly noiseless record makes the per-cycle
    difference series exactly constant, and the batch-means estimator REFUSES that -- "not
    a real limit cycle" -- which is the correct behaviour and the reason a synthetic
    fixture has to carry variance to exercise the paired path at all.
    """
    t = np.linspace(0.0, cycles * period, cycles * 400, endpoint=False)
    rng = np.random.default_rng(seed)
    jitter = rng.normal(0.0, 0.01 * max(abs(offset), 0.1), size=t.size)
    thrust = offset + amplitude * np.cos(2.0 * np.pi * t / period) + jitter
    power = 2.0 * offset + amplitude * np.sin(2.0 * np.pi * t / period) + jitter
    return t, {"thrust": thrust, "power": power}


class TestTheDefaultPathIsUnchanged:
    def test_the_detected_period_is_still_the_default(self) -> None:
        t, signals = _record()
        analysis = analyse_limit_cycle(t, signals, fundamental="thrust", min_cycles=4)
        assert analysis.period_source == "detected"
        assert analysis.fundamental_frequency == pytest.approx(FREQUENCY, rel=1e-2)
        assert analysis.fundamental_frequency == analysis.detected_frequency

    def test_the_period_and_the_frequency_stay_reciprocal(self) -> None:
        t, signals = _record()
        analysis = analyse_limit_cycle(t, signals, fundamental="thrust")
        assert analysis.period == pytest.approx(1.0 / analysis.fundamental_frequency)


class TestAPrescribedPeriod:
    def test_it_is_used_verbatim(self) -> None:
        t, signals = _record()
        analysis = analyse_limit_cycle(t, signals, fundamental="thrust", period=PERIOD)
        assert analysis.period == PERIOD  # bitwise: it is the number that was passed in
        assert analysis.period_source == "prescribed"

    def test_the_detected_frequency_is_still_measured_and_reported(self) -> None:
        # Reported rather than used: a prescribed period far from the detected one is a
        # finding about the solve, and silently discarding the measurement would hide it.
        t, signals = _record()
        analysis = analyse_limit_cycle(t, signals, fundamental="thrust", period=PERIOD)
        assert analysis.detected_frequency == pytest.approx(FREQUENCY, rel=1e-2)

    def test_two_arms_get_bitwise_identical_periods(self) -> None:
        # The whole point. Detected periods differ in the last digits between arms; a
        # prescribed one is the same float, which is what rtol=1e-9 requires.
        t_a, sig_a = _record(amplitude=1.0, offset=0.5, seed=1)
        t_b, sig_b = _record(amplitude=1.3, offset=0.9, seed=2)
        a = analyse_limit_cycle(t_a, sig_a, fundamental="thrust", period=PERIOD)
        b = analyse_limit_cycle(t_b, sig_b, fundamental="thrust", period=PERIOD)
        assert a.period == b.period

    def test_a_nonpositive_prescribed_period_is_refused(self) -> None:
        t, signals = _record()
        with pytest.raises(LimitCycleError, match="must be positive"):
            analyse_limit_cycle(t, signals, fundamental="thrust", period=-1.0)


class TestThePairedPathIsNowCallable:
    def test_the_per_cycle_objects_survive(self) -> None:
        t, signals = _record()
        analysis = analyse_limit_cycle(t, signals, fundamental="thrust", period=PERIOD)
        assert isinstance(analysis.cycles_of("thrust"), CycleSamples)
        assert isinstance(analysis.convergence, CycleConvergenceReport)
        assert set(analysis.cycles) == set(analysis.statistics)

    def test_paired_delta_uncertainty_can_actually_be_called(self) -> None:
        # Before this commit the four arguments it needs did not exist outside the
        # function that computed them, so this call was impossible to write.
        t_a, sig_a = _record(amplitude=1.0, offset=0.40, seed=1)
        t_b, sig_b = _record(amplitude=1.0, offset=0.55, seed=2)
        a = analyse_limit_cycle(t_a, sig_a, fundamental="thrust", period=PERIOD)
        b = analyse_limit_cycle(t_b, sig_b, fundamental="thrust", period=PERIOD)

        delta = paired_delta_uncertainty(
            a.cycles_of("thrust"), a.convergence, b.cycles_of("thrust"), b.convergence
        )
        assert delta.n_pairs >= 4
        assert delta.mean_candidate - delta.mean_baseline == pytest.approx(0.15, abs=5e-3)
        assert delta.period == PERIOD  # the arms were segmented on the SAME prescribed period

    def test_the_statistics_still_agree_with_the_kept_cycles(self) -> None:
        # The cycles are the objects the statistics were computed FROM, so a mean of the
        # per-cycle means must reproduce the reported mean exactly.
        t, signals = _record(offset=0.3)
        analysis = analyse_limit_cycle(t, signals, fundamental="thrust", period=PERIOD)
        cycles = analysis.cycles_of("thrust")
        assert float(np.mean(cycles.per_cycle_mean)) == pytest.approx(
            analysis.of("thrust").mean, rel=1e-12
        )

    def test_an_unknown_signal_is_refused_by_name(self) -> None:
        t, signals = _record()
        analysis = analyse_limit_cycle(t, signals, fundamental="thrust", period=PERIOD)
        with pytest.raises(LimitCycleError, match="no signal 'lift'"):
            analysis.cycles_of("lift")

    def test_the_convergence_anchor_is_available_for_alignment(self) -> None:
        # converged_from_cycle is the segmentation ANCHOR; the two arms generally settle
        # at different cycles, so pairing by index without it is silently phase-shifted.
        t, signals = _record()
        analysis = analyse_limit_cycle(t, signals, fundamental="thrust", period=PERIOD)
        assert analysis.convergence.converged_from_cycle >= 0
        assert analysis.convergence.n_cycles >= analysis.n_settled_cycles

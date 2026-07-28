"""Unit tests for `aero.postprocess.limit_cycle`.

The interesting cases are not "does it compute a mean" but the three properties the
FSI3 gate depends on: one period for every signal, a window derived by rule, and a
refusal to report on a record that has not settled.
"""

from __future__ import annotations

import numpy as np
import pytest
from aero.postprocess import LimitCycleError, analyse_limit_cycle

pytestmark = pytest.mark.stage_19

_F0 = 5.0
_AMPLITUDE = 0.035
_MEAN = 1.5e-3


def _record(
    *, duration: float = 4.0, dt: float = 1e-3, growth_until: float = 0.0, t0: float = 0.0
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """A transverse fundamental plus a second-harmonic streamwise companion.

    `growth_until` ramps the amplitude linearly, standing in for a solve still building
    towards its limit cycle.
    """
    t = np.arange(t0, t0 + duration, dt)
    envelope = np.ones_like(t)
    if growth_until > t0:
        ramp = np.clip((t - t0) / (growth_until - t0), 0.0, 1.0)
        envelope = 0.2 + 0.8 * ramp
    uy = _MEAN + _AMPLITUDE * envelope * np.sin(2 * np.pi * _F0 * t)
    # Streamwise tip motion is dominated by the second harmonic and is much smaller.
    # The small fundamental component is not decoration: the benchmark cylinder sits
    # 0.005 m below mid-channel, so the flag's two half-strokes are not identical and
    # the streamwise response carries a 1f term. That asymmetry is what makes
    # consecutive 2f-cycles differ, and it is what the segmentation trap is made of.
    ux = (
        -2.9e-3
        + 2.7e-3 * envelope * np.sin(2 * np.pi * 2 * _F0 * t)
        + 0.35e-3 * envelope * np.sin(2 * np.pi * _F0 * t)
    )
    return t, {"uy": uy, "ux": ux}


def test_recovers_a_clean_limit_cycle() -> None:
    t, signals = _record(duration=6.0)
    analysis = analyse_limit_cycle(t, signals, fundamental="uy", min_cycles=4)

    assert analysis.fundamental_frequency == pytest.approx(_F0, rel=0.02)
    uy = analysis.of("uy")
    assert uy.amplitude == pytest.approx(_AMPLITUDE, rel=0.02)
    assert uy.mean == pytest.approx(_MEAN, abs=2e-4)
    assert analysis.n_settled_cycles >= 4


def test_every_signal_is_segmented_at_the_fundamental_period() -> None:
    """The whole point of the module.

    `ux` here is a pure second harmonic. Segmented at its OWN frequency its per-cycle
    amplitudes alternate between half-strokes and the drift check fails; segmented at
    the fundamental it is stable. Measured on the published FSI3 reference too:
    amplitude drift 0.070 for ux and 0.163 for drag, against a 0.02 tolerance.
    """
    t, signals = _record(duration=6.0)
    analysis = analyse_limit_cycle(t, signals, fundamental="uy", min_cycles=4)

    assert analysis.of("ux").frequency == pytest.approx(2 * _F0, rel=0.02)
    # ...but it was measured over cycles of the FUNDAMENTAL period, so it survives.
    # The peak-to-peak sits a little above the 2.7e-3 harmonic term because the 0.35e-3
    # fundamental component adds to it on one half-stroke.
    assert 2.7e-3 <= analysis.of("ux").amplitude <= 3.1e-3
    assert analysis.period == pytest.approx(1.0 / _F0, rel=0.02)

    # And nominating the harmonic as the fundamental is what fails: at the 2f period,
    # consecutive cycles straddle opposite half-strokes, so their amplitudes alternate
    # and the drift check trips — on a record that is, by construction, perfectly
    # periodic.
    with pytest.raises(LimitCycleError, match="no periodic steady state"):
        analyse_limit_cycle(
            t,
            {"ux": signals["ux"], "uy": signals["uy"]},
            fundamental="ux",
            min_cycles=4,
        )


def test_a_drifting_record_is_refused() -> None:
    """A number read off a record that is still growing is not a limit-cycle measurement."""
    t, signals = _record(duration=3.0, growth_until=3.0)
    with pytest.raises(LimitCycleError, match="no periodic steady state"):
        analyse_limit_cycle(t, signals, fundamental="uy", min_cycles=4)


def test_the_discard_is_absolute_solver_time() -> None:
    """`discard_s` means "before this instant", not "this long after the first sample".

    The published reference series starts at t = 5 s; a solve starts at t = 0. The same
    pre-registered rule has to mean the same thing for both.
    """
    t, signals = _record(duration=6.0, t0=5.0)
    analysis = analyse_limit_cycle(t, signals, fundamental="uy", discard_s=4.0, min_cycles=4)
    assert analysis.t_start >= 5.0

    analysis_late = analyse_limit_cycle(t, signals, fundamental="uy", discard_s=8.0, min_cycles=4)
    assert analysis_late.t_start >= 8.0


def test_discarding_everything_is_loud() -> None:
    t, signals = _record(duration=2.0)
    with pytest.raises(LimitCycleError, match="leaves no samples"):
        analyse_limit_cycle(t, signals, fundamental="uy", discard_s=99.0)


def test_the_discard_dominates_the_detector() -> None:
    """The pre-registered rule wins even where the detector would have accepted earlier.

    That asymmetry is deliberate: the discard is a commitment made before seeing the
    record, so it may only ever move the window later, never earlier.
    """
    t, signals = _record(duration=8.0, growth_until=3.0)

    # Left to itself the detector finds the settled tail after the ramp — which is
    # correct, and is why "no periodic steady state" is not the failure mode here.
    unconstrained = analyse_limit_cycle(t, signals, fundamental="uy", min_cycles=4)
    assert unconstrained.t_start > 2.5

    constrained = analyse_limit_cycle(t, signals, fundamental="uy", discard_s=6.0, min_cycles=3)
    assert constrained.t_start >= 6.0
    assert constrained.t_start > unconstrained.t_start
    assert constrained.of("uy").amplitude == pytest.approx(_AMPLITUDE, rel=0.03)


def test_min_cycles_is_enforced() -> None:
    t, signals = _record(duration=6.0)
    with pytest.raises(LimitCycleError, match="need 50"):
        analyse_limit_cycle(t, signals, fundamental="uy", min_cycles=50)


def test_unknown_fundamental_is_loud() -> None:
    t, signals = _record()
    with pytest.raises(LimitCycleError, match="not among"):
        analyse_limit_cycle(t, signals, fundamental="nope")


def test_analysis_window_is_the_settled_tail_not_the_whole_record() -> None:
    t, signals = _record(duration=10.0, growth_until=4.0)
    analysis = analyse_limit_cycle(t, signals, fundamental="uy", discard_s=0.0, min_cycles=3)
    # The window must start after the ramp, without anyone having said where.
    assert analysis.t_start > 3.0
    assert analysis.t_end == pytest.approx(float(t[-1]), abs=1e-9)
    assert analysis.window_duration < float(t[-1] - t[0])


# --- the cumulative bound (ADR-036 S5) ----------------------------------------------


def _growing(rate_per_cycle: float, *, duration: float = 8.0, f0: float = 5.539872):
    """A record whose amplitude grows steadily and never saturates."""
    t = np.arange(0.001, duration, 1e-3)
    grow = (1.0 + rate_per_cycle) ** (t * f0)
    uy = 9.66436e-4 + 0.671 * 3.495533e-2 * grow * np.sin(2 * np.pi * f0 * t)
    ux = (
        -2.8568e-3
        + 2.7002e-3 * grow * np.sin(2 * np.pi * 2 * f0 * t)
        + 0.35e-3 * grow * np.sin(2 * np.pi * f0 * t)
    )
    return t, {"flap_tip_uy": uy, "flap_tip_ux": ux}


def test_sub_tolerance_monotone_growth_is_refused() -> None:
    """The defect an adversarial review found in this gate, pinned.

    detect_cycle_convergence compares ADJACENT cycles only. At 1.2 % growth per cycle
    every adjacent difference sits inside the 2 % tolerance, so the record certified as a
    fully settled limit cycle while its amplitude grew ~30 % across the analysis window —
    and all five displacement bands then passed, producing a GO on a solve that never
    reached a periodic steady state. A slowly saturating added-mass instability is the
    realistic FSI3 failure mode, not a contrived signal.
    """
    t, signals = _growing(0.012)
    with pytest.raises(LimitCycleError, match="drifts monotonically"):
        analyse_limit_cycle(t, signals, fundamental="flap_tip_uy", discard_s=4.0, min_cycles=4)


def test_the_cumulative_bound_still_accepts_a_genuine_limit_cycle() -> None:
    """A bound that refused real data would be worse than no bound."""
    t, signals = _record(duration=8.0)
    analysis = analyse_limit_cycle(t, signals, fundamental="uy", discard_s=4.0, min_cycles=4)
    assert analysis.cumulative_amplitude_drift < 0.02
    assert analysis.cumulative_mean_drift < 0.02


def test_settled_cycle_count_is_the_cycles_actually_averaged() -> None:
    """n_settled_cycles is provenance-bearing: it must not overstate the evidence.

    The detector counts on a segmentation anchored at the first kept sample; the
    statistics are computed on a re-segmentation anchored at the window start. Those can
    differ by one.
    """
    t, signals = _record(duration=8.0)
    analysis = analyse_limit_cycle(t, signals, fundamental="uy", discard_s=4.0, min_cycles=4)
    assert analysis.n_settled_cycles == analysis.of("uy").n_cycles

"""The settling fixture two Stage-20 test modules share.

Anchors its transient at the DISCARD boundary so ``converged_from_cycle > 0`` (a fixture
with no transient cannot test transient-dependent indexing), and uses a non-integer
record length so fractional-cycle weighting is expressible (the §6.20 lessons).
"""

from __future__ import annotations

import numpy as np
from aero.postprocess import analyse_limit_cycle
from aero.vv.fsi.hg2007_readout import C_P, C_P1, C_T, P3

_PERIOD = 1.0
_DT = 1.0e-3
_DISCARD = 2.0 * _PERIOD
_RNG = np.random.default_rng(20260810)


def _fixture():  # type: ignore[no-untyped-def]
    # 14.37 periods: the tail re-segmentation keeps integer cycles and drops the .37.
    t = np.arange(0.0, 14.37 * _PERIOD, _DT)
    # Anchored at the DISCARD boundary so cycle 0 of the post-discard record is still
    # settling (converged_from_cycle > 0), while the decay-within-a-cycle shape keeps the
    # cumulative drift bound satisfied over the tail (§6.20).
    transient = 0.25 * np.exp(-np.maximum(t - _DISCARD, 0.0) / (0.30 * _PERIOD))
    noise = 0.004 * _RNG.standard_normal(t.size)  # the estimator refuses noiseless records

    def signal(mean: float, amplitude: float, phase: float) -> np.ndarray:
        return (
            mean
            + amplitude * np.sin(2.0 * np.pi * t / _PERIOD + phase)
            + transient * amplitude
            + noise * amplitude
        )

    signals = {
        "d0": signal(0.0, 5.0, 0.0),
        C_T: signal(1.0, 6.0, 0.7),
        C_P: signal(5.7, 9.0, 1.1),
        C_P1: signal(5.5, 9.0, 1.3),
        P3: signal(0.0057, 0.009, 1.1),
    }
    analysis = analyse_limit_cycle(
        t,
        signals,
        fundamental="d0",
        discard_s=_DISCARD,
        min_cycles=4,
        period=_PERIOD,
    )
    return t, signals, analysis

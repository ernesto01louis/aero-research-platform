"""Limit-cycle analysis of a preCICE displacement watch-point.

A thin, deliberately boring bridge from :class:`~aero.adapters.precice.watchpoint.
WatchpointTrace` to :func:`aero.postprocess.analyse_limit_cycle`. It exists so that the
rule-derived analysis window, the single-fundamental-period segmentation and the
fail-loud periodic-steady-state check are applied by exactly one code path — the same
one that produced the published reference of record in
``data/references/fsi/turek_hron_fsi3/fsi3_recomputed.csv``.

The transverse component is the fundamental: the flag's streamwise tip displacement
oscillates at twice the transverse frequency, so it must not be used to set the period
(see :mod:`aero.postprocess.limit_cycle`).
"""

from __future__ import annotations

import numpy as np

from aero.adapters.precice.watchpoint import WatchpointError, WatchpointTrace
from aero.postprocess import LimitCycleAnalysis, analyse_limit_cycle

#: Column names preCICE writes for a 2-D vector datum named "Displacement".
DISPLACEMENT_X_COLUMN = "Displacement0"
DISPLACEMENT_Y_COLUMN = "Displacement1"

TIP_UX = "flap_tip_ux"
TIP_UY = "flap_tip_uy"

#: Stage-20 signal names. `D0_PITCH` is the chord line's angle, from the nose watch-point to
#: the trailing-edge one -- the pitch the flexibility PRODUCED, which is the whole point of
#: the experiment and is never prescribed. It is also the right fundamental: it oscillates at
#: the plunge frequency, whereas thrust is at twice it.
D0_PITCH = "te_pitch_deg"
NOSE_UY = "nose_uy"
TE_UX = "te_ux"


def analyse_displacement_watchpoint(
    trace: WatchpointTrace,
    *,
    discard_s: float,
    min_cycles: int,
    x_column: str = DISPLACEMENT_X_COLUMN,
    y_column: str = DISPLACEMENT_Y_COLUMN,
) -> LimitCycleAnalysis:
    """Analyse a 2-D displacement watch-point over its settled limit cycle.

    Raises :class:`~aero.postprocess.LimitCycleError` if no periodic steady state with at
    least `min_cycles` settled cycles exists after `discard_s`.
    """
    missing = [c for c in (x_column, y_column) if c not in trace.values]
    if missing:
        raise WatchpointError(
            f"{trace.path}: watch-point has no column(s) {', '.join(missing)} "
            f"(have: {', '.join(sorted(trace.values))}). A displacement analysis needs "
            "both components of the tracked point."
        )
    t = np.asarray(trace.t, dtype=np.float64)
    return analyse_limit_cycle(
        t,
        {
            TIP_UY: np.asarray(trace.values[y_column], dtype=np.float64),
            TIP_UX: np.asarray(trace.values[x_column], dtype=np.float64),
        },
        # Transverse is the fundamental; streamwise is its second harmonic.
        fundamental=TIP_UY,
        discard_s=discard_s,
        min_cycles=min_cycles,
    )

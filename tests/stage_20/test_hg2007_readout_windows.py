"""The gated means come from the settled integer-cycle tail, never a flat sample mean.

Session-7 adversarial-review candidates 12 and 13, both verified against the code before
this fix: ``eta`` was a ratio over the WHOLE post-discard per-cycle record (unconverged
cycles included) while every sibling mean used the settled window, and the sibling means
themselves were flat sample means over ``[t_start, t_end]`` — a window that generically
ends mid-cycle, so an oscillating signal contributes a phase-dependent partial-cycle
bias straight into D1, D5 and both legs of the D10 closure. The correct estimator —
``of(name).mean``, integer cycles on the tail re-segmentation — was computed and ignored.

The fixture is built so both defects are VISIBLE (the §6.20 lesson: a fixture with no
transient cannot test transient-dependent indexing, and a fixture with integer-period
length cannot test fractional-cycle weighting): the transient is anchored at the discard
boundary so it survives INTO the post-discard record and the detector reports a nonzero
``converged_from_cycle``, and the record length is deliberately not an integer number of
periods.
"""

from __future__ import annotations

import numpy as np
import pytest
from aero.vv.fsi.hg2007_readout import C_P, C_P1, C_T, P3, gated_means

from tests.stage_20._settling import _fixture

pytestmark = pytest.mark.stage_20


def test_the_fixture_actually_carries_a_post_discard_transient() -> None:
    """Without ``converged_from_cycle > 0`` the eta property below is vacuously true."""
    _, _, analysis = _fixture()
    assert analysis.convergence.converged_from_cycle > 0


def test_gated_means_are_the_integer_cycle_tail_estimator() -> None:
    _, _, analysis = _fixture()
    means = gated_means(analysis)
    expected = tuple(analysis.of(name).mean for name in (C_T, C_P, C_P1, P3))
    assert means == expected


def test_the_flat_sample_mean_would_have_been_a_different_number() -> None:
    """The RAW-series flat mean over [t_start, t_end] — the pre-fix estimator — differs.

    The window ends 0.37 of a cycle past the last full one, and the fixture's
    amplitude-to-mean ratio is 6:1, so the partial cycle must move a flat mean visibly.
    """
    t, signals, analysis = _fixture()
    keep = (t >= analysis.t_start) & (t <= analysis.t_end)
    flat = float(np.mean(signals[C_T][keep]))
    tail = analysis.of(C_T).mean
    assert flat != pytest.approx(tail, rel=1.0e-3)


def test_eta_is_the_ratio_of_the_same_two_tail_means() -> None:
    """D2's eta is c_t/c_p over ONE settled window — not over the post-discard record."""
    _, _, analysis = _fixture()
    c_t_mean, c_p_mean, _, _ = gated_means(analysis)
    eta_tail = c_t_mean / c_p_mean
    whole_ct = np.asarray(analysis.cycles[C_T].per_cycle_mean, dtype=np.float64)
    whole_cp = np.asarray(analysis.cycles[C_P].per_cycle_mean, dtype=np.float64)
    eta_whole_record = float(np.mean(whole_ct) / np.mean(whole_cp))
    # The post-discard record includes the still-settling cycle(s) the tail excludes, and
    # the two signals carry the transient at different relative sizes, so the pre-fix
    # whole-record ratio must differ from the settled ratio.
    assert eta_whole_record != pytest.approx(eta_tail, rel=1.0e-4)

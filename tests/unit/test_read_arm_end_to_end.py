"""`read_arm`, executed end to end — the first time it has completed on any input.

Session 9 found (§6.35) that `--collect` -> `read_arm` would have RAISED on both surviving
I4 arms after wave 1's weeks of wall clock. Session 10 fixed the window join and proved it
against those arms' real bytes. Everything DOWNSTREAM of the join — `analyse_limit_cycle`
on the joined base, `gated_means`, P1/P2/P3 and the D10 closure — was still unexecuted, on
any input, and this session confirmed why it will stay that way until the campaign runs:
`load()` refuses anything shorter than `analysis_discard_s + analysis_min_cycles * period`,
which at the campaign's numbers is 13.19 s, about 660 000 windows. Every probe that has
ever run is 0.01 s.

So the case here is SYNTHETIC, and the honest limit is stated plainly: this proves the code
against bytes this repo wrote, not against a solver. What it does prove is worth having.
The path runs. And because the series are analytic, the numbers are checkable rather than
merely produced — in particular

    P3 == P2 by construction, so D10 must close.

`aero/vv/fsi/hg2007_readout.py`'s header states that identity holds exactly under ALPHA = 0
with no damping. Until now nothing had ever evaluated it.

In `tests/unit/` because `tests/stage_20` is not in CI (handoff §6.24).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from aero.postprocess.limit_cycle import LimitCycleError
from aero.vv.fsi.hg2007_readout import ArmReadout, read_arm

from tests.unit._hg2007_case_tree import DISCARD_S, DT, MIN_CYCLES, N_WINDOWS, PERIOD, build

pytestmark = pytest.mark.stage_20


@pytest.fixture(scope="module")
def readout(tmp_path_factory: pytest.TempPathFactory) -> ArmReadout:
    root = tmp_path_factory.mktemp("hg2007")
    solver, result, _spec = build(root)
    return read_arm(solver, result, arm="flexible")


# --------------------------------------------------------------------------------------
# It completes, and it completes through the join
# --------------------------------------------------------------------------------------


def test_read_arm_completes(readout: ArmReadout) -> None:
    """The claim this file exists to make."""
    assert isinstance(readout, ArmReadout)
    assert readout.arm == "flexible"


def test_every_window_survived_the_join(readout: ArmReadout) -> None:
    """The fluid's trailing stamp is dropped and nothing else is."""
    assert readout.n_windows_analysed == N_WINDOWS
    assert readout.force_cadence == "per-iteration"


def test_the_analysis_time_base_is_the_window_end_instant(readout: ArmReadout) -> None:
    """§6.38's fix, observed at the far end of the path rather than at the join.

    The fluid stamps the window START and CalculiX the window END. `read_arm` rebuilds the
    analysis base from the window INDEX, so the first analysed instant is dt — not the 0 the
    fluid's own record carries. Before the join they differed by one window, which was a
    signed bias in D9 and D10.
    """
    assert readout.force_t[0] == pytest.approx(DT)
    assert readout.force_t[-1] == pytest.approx(N_WINDOWS * DT)


def test_the_settled_tail_is_what_the_rule_yields_not_the_whole_record(
    readout: ArmReadout,
) -> None:
    """Eight cycles survive the discard; the detector keeps the settled ones and says how many."""
    assert readout.n_settled_cycles >= MIN_CYCLES
    assert readout.t_start >= DISCARD_S
    assert readout.period == pytest.approx(PERIOD)
    assert readout.t_end - readout.t_start == pytest.approx(readout.n_settled_cycles * PERIOD)


# --------------------------------------------------------------------------------------
# The numbers, not just the plumbing
# --------------------------------------------------------------------------------------


def test_the_d10_closure_closes(readout: ArmReadout) -> None:
    """P3 == P2 by construction, so |P3-P2|/P2 must be ~0 — and it is, to 1e-6.

    It is not ~1e-16, and the reason is a real property of the measurement chain rather
    than of this fixture: CalculiX prints its reaction forces to SEVEN significant digits
    (`ccx_dat._PRINT_SIGNIFICANT_DIGITS`), so P3 is reconstructed from a 7-digit number
    while P2 rides in the fluid log at full precision. That sets a floor of order 1e-7 on
    how tightly D10 can ever close on real bytes. ADR-039's D10 band is 2 %, five orders
    of magnitude above the floor, so the identity is comfortably measurable — which is
    the thing worth knowing, and it had never been checked.
    """
    assert abs(readout.p3_p2_closure) < 1.0e-6


def test_the_d9_bias_is_a_real_number_and_not_zero(readout: ArmReadout) -> None:
    """D9 exists to show the naive rigid-body power formula is biased. It must be able to.

    P1 uses the PRESCRIBED plunge velocity against the interface force; P2 is what the
    fluid actually did on the wall. A path that returned 0 here would mean D9 could never
    report the bias it was added to report.
    """
    assert np.isfinite(readout.p1_p2_bias)
    assert abs(readout.p1_p2_bias) > 1.0e-3


def test_eta_is_the_ratio_of_the_same_two_tail_means(readout: ArmReadout) -> None:
    """Ratio of means, never mean of ratios (session-7 adversarial review, candidate 12)."""
    assert readout.eta == pytest.approx(readout.c_t / readout.c_p)


def test_the_gated_means_come_from_the_settled_tail(readout: ArmReadout) -> None:
    """Every gated number is finite and drawn from the analysis window, not the record."""
    for value in (readout.c_t, readout.c_p, readout.c_p1, readout.d0_pitch_amplitude_deg):
        assert np.isfinite(value)
    assert readout.c_p != 0.0, "the zero guard would have raised; this pins that it need not"
    assert readout.analysis.t_start == readout.t_start


# --------------------------------------------------------------------------------------
# And the refusal a real probe gets, on the same machinery
# --------------------------------------------------------------------------------------


def test_the_d10_assertion_can_fail(tmp_path: Path) -> None:
    """A closure test on a fixture built to close is worth nothing if it cannot detect a gap.

    The reaction record is re-written with a 5 % error and nothing else is touched. D10
    must move to ~5 % — past this file's 1e-6 assertion AND past ADR-039's 2 % band, which
    is what says the gate would catch the same defect on real bytes.
    """
    solver, result, spec = build(tmp_path)
    dat = (
        tmp_path
        / "tutorial"
        / spec.case_subdir
        / "solid-calculix"
        / f"{spec.source.solid.name}.dat"
    )
    rewritten = []
    for line in dat.read_text().splitlines():
        parts = line.split()
        if len(parts) == 3 and not line.lstrip().startswith("total"):
            fx, fy, fz = (float(p) for p in parts)
            rewritten.append(f"       {fx:.6E} {fy * 1.05:.6E} {fz:.6E}")
        else:
            rewritten.append(line)
    dat.write_text("\n".join(rewritten) + "\n", encoding="utf-8")

    broken = read_arm(solver, result, arm="flexible")
    assert abs(broken.p3_p2_closure) == pytest.approx(0.05, abs=1e-4)
    assert abs(broken.p3_p2_closure) > 0.02, "ADR-039's D10 band would not have caught this"


def test_a_record_shorter_than_the_discard_is_refused_before_anything_is_read(
    tmp_path: Path,
) -> None:
    """What every probe that has ever run gets, reproduced without a cluster.

    `read_arm` calls `load()` first — its docstring says the ordering is the point — and
    `load()` runs `analyse_limit_cycle` with the S2 discard on the watch-point base. A run
    that has not passed the start-up transient is refused THERE, upstream of the join, so
    the join and everything after it never execute. The Q1 arms (0.01 s against a 3.0435 s
    discard) refuse with exactly this message.
    """
    solver, result, _spec = build(tmp_path, discard_s=N_WINDOWS * DT * 10.0)
    with pytest.raises(LimitCycleError, match="has not passed the start-up transient"):
        read_arm(solver, result, arm="flexible")

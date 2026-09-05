"""ADR-041 V2/V4 — the solid-side parity divergence detector.

The flexible arm of N3 attempt 1 (`fsi-hg2007_flexible_foil-20260812-230102`) died at
window 1703 of 76 090 with a CalculiX heap abort, and handoff §6.49 established that a
period-2, odd-window instability had been running for ~150 windows before it while every
interface-side series stayed clean. This detector is what would have seen it.

Two properties matter more than the parsing:

* It is a **ratio** test, never an absolute-newton one. The healthy residual envelope
  tracks the commanded load — on the dead arm it climbed 0.65 → 24.49 N over the first
  1500 windows, and full campaign amplitude is another 464x beyond that — so a fixed
  threshold either fires on healthy full-amplitude operation or sleeps through a
  divergence. §6.49's own "a 443 N watchdog would have fired at ~w1650" is refuted by the
  table it came from: the first window above 443 N is w1683, 20 windows before death.
* It says **INCONCLUSIVE rather than clean** when it cannot discriminate. On the rigid
  control's complete 76 090-window run only 4.8 % of chunks reach the activation floor;
  reporting that as health would be a lie of omission about a barely-deforming solid.

The fixtures below are synthetic but shaped like the real logs, including the ANSI escape
bytes preCICE writes into its window-marker lines. The bounds are pinned as literals: a
test that re-derived them from the same constants would pass whatever they became.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aero.adapters.precice.logs import (
    ACTIVATION_FLOOR_N,
    BLOCK_GROWTH_LIMIT,
    GRID_START_WINDOW,
    PARITY_CONSECUTIVE_CHUNKS,
    PARITY_RATIO_LIMIT,
    SolidLogError,
    evaluate_divergence,
    read_solid_residuals,
    solid_log_path,
)

pytestmark = pytest.mark.stage_20

_MARKER = (
    "---[precice] \x1b[0m it {it} (min: 1, max: 50), time-window {w}, "
    "t {t} (max: 1.5218), Dt 2e-05, max-dt 2e-05\n"
)
_RESIDUAL = " largest residual force= {value:.6f} in node {node} and dof 2\n"


def _log(path: Path, per_window: dict[int, float], *, node: int = 2030) -> Path:
    """Write a Solid.log carrying exactly these per-window maxima."""
    lines: list[str] = []
    for window in sorted(per_window):
        lines.append(_MARKER.format(it=1, w=window, t=window * 2e-5))
        # a smaller residual first, so the reader has to take the maximum rather than the last
        lines.append(_RESIDUAL.format(value=per_window[window] * 0.5, node=node + 1))
        lines.append(_RESIDUAL.format(value=per_window[window], node=node))
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _flat(first: int, last: int, value: float) -> dict[int, float]:
    return {w: value for w in range(first, last + 1)}


def test_the_parser_reproduces_the_reference_extraction(tmp_path: Path) -> None:
    """Window attribution across ANSI-escaped markers; maxima, argmax node, |residual|.

    This mirrors session 12's `minerB_parse.awk` (sha256 0d6eeca9…), which is the
    normative definition in ADR-041 V2 and which this implementation reproduces on all
    1703 windows of the dead arm at that table's own printed precision.
    """
    path = tmp_path / "Solid.log"
    text = (
        _MARKER.format(it=1, w=101, t=0.00202)
        + _RESIDUAL.format(value=3.0, node=111)
        + " no convergence\n"
        + _RESIDUAL.format(value=-9.5, node=222)  # ccx can sign these; the census is absolute
        + _MARKER.format(it=2, w=101, t=0.00202)  # a second coupling iteration, same window
        + _RESIDUAL.format(value=4.0, node=333)
        + _MARKER.format(it=1, w=102, t=0.00204)
        + " 1.5e8 0.0 RESID.FORCE percentage-shaped row that is NOT a residual line\n"
        + _RESIDUAL.format(value=1.25, node=444)
    )
    path.write_text(text, encoding="utf-8")

    series = read_solid_residuals(path)

    assert [w.window for w in series.windows] == [101, 102]
    first, second = series.windows
    assert first.max_abs_residual == pytest.approx(9.5)
    assert first.argmax_node == 222
    assert first.n_residuals == 3
    assert first.n_no_convergence == 1
    assert second.max_abs_residual == pytest.approx(1.25)
    assert series.is_contiguous


def test_a_missing_or_empty_log_is_loud_never_silently_healthy(tmp_path: Path) -> None:
    with pytest.raises(SolidLogError, match=r"no Solid\.log"):
        read_solid_residuals(tmp_path / "Solid.log")

    started = tmp_path / "Solid.log"
    started.write_text("CalculiX Version 2.20\n", encoding="utf-8")
    with pytest.raises(SolidLogError, match="never advanced a window"):
        read_solid_residuals(started)


def test_the_parity_prong_needs_two_consecutive_chunks(tmp_path: Path) -> None:
    """One chunk over the limit is not a verdict — under V1 a rung verdict is final."""
    values = _flat(1, 200, 5.0)
    for w in range(GRID_START_WINDOW, GRID_START_WINDOW + 20, 2):  # one chunk, odd branch up
        values[w] = 5.0 * (PARITY_RATIO_LIMIT + 1.0)

    report = evaluate_divergence(read_solid_residuals(_log(tmp_path / "Solid.log", values)))

    assert report.verdict == "clean"
    assert report.worst_parity_ratio == pytest.approx(PARITY_RATIO_LIMIT + 1.0)
    assert not report.findings


def test_two_consecutive_chunks_fire_and_name_the_window(tmp_path: Path) -> None:
    values = _flat(1, 200, 5.0)
    for w in range(GRID_START_WINDOW, GRID_START_WINDOW + 40, 2):  # two chunks
        values[w] = 5.0 * (PARITY_RATIO_LIMIT + 1.0)

    report = evaluate_divergence(read_solid_residuals(_log(tmp_path / "Solid.log", values)))

    assert report.verdict == "precursor"
    assert report.fired
    fired = [f for f in report.findings if f.prong == "parity"]
    assert len(fired) == 1
    # the SECOND chunk's last window: w101-120 then w121-140
    assert fired[0].fired_at_window == GRID_START_WINDOW + 2 * 20 - 1
    assert f"{PARITY_CONSECUTIVE_CHUNKS} consecutive" in fired[0].detail


def test_an_inactive_chunk_between_them_breaks_the_pair(tmp_path: Path) -> None:
    """CONSECUTIVE means grid-adjacent AND both active — inactive chunks are never skipped.

    Without this the detector would join two divergent chunks across an arbitrarily long
    quiet stretch, which on the rigid control would have spanned 723 blocks.
    """
    values = _flat(1, 200, 5.0)
    hot = 5.0 * (PARITY_RATIO_LIMIT + 1.0)
    for w in range(GRID_START_WINDOW, GRID_START_WINDOW + 20, 2):  # chunk 1: hot
        values[w] = hot
    for w in range(GRID_START_WINDOW + 20, GRID_START_WINDOW + 40):  # chunk 2: below the floor
        values[w] = ACTIVATION_FLOOR_N / 10.0
    for w in range(GRID_START_WINDOW + 40, GRID_START_WINDOW + 60, 2):  # chunk 3: hot again
        values[w] = hot

    report = evaluate_divergence(read_solid_residuals(_log(tmp_path / "Solid.log", values)))

    assert report.verdict != "precursor"
    assert not [f for f in report.findings if f.prong == "parity"]


def test_the_runaway_prong_fires_on_same_parity_block_growth(tmp_path: Path) -> None:
    values = _flat(1, 300, 5.0)
    for w in range(GRID_START_WINDOW + 100, GRID_START_WINDOW + 200):  # the next block
        values[w] = 5.0 * (BLOCK_GROWTH_LIMIT + 0.5)

    report = evaluate_divergence(read_solid_residuals(_log(tmp_path / "Solid.log", values)))

    runaway = [f for f in report.findings if f.prong == "runaway"]
    assert report.verdict == "precursor"
    assert runaway and runaway[0].value == pytest.approx(BLOCK_GROWTH_LIMIT + 0.5)


def test_growth_never_accumulates_across_an_inactive_block(tmp_path: Path) -> None:
    """A gap firewalls the comparison; the nearest earlier active block is not substituted."""
    values = _flat(1, 300, 5.0)
    for w in range(GRID_START_WINDOW + 100, GRID_START_WINDOW + 200):  # quiet middle block
        values[w] = ACTIVATION_FLOOR_N / 10.0
    for w in range(GRID_START_WINDOW + 200, GRID_START_WINDOW + 300):  # far above the FIRST block
        values[w] = 5.0 * (BLOCK_GROWTH_LIMIT + 5.0)

    report = evaluate_divergence(read_solid_residuals(_log(tmp_path / "Solid.log", values)))

    assert not [f for f in report.findings if f.prong == "runaway"]


def test_low_activation_is_inconclusive_not_clean(tmp_path: Path) -> None:
    """The rigid control's shape: real, healthy, and unable to discriminate (V2 (iii))."""
    values = _flat(1, 500, ACTIVATION_FLOOR_N / 100.0)
    for w in range(GRID_START_WINDOW, GRID_START_WINDOW + 40):
        values[w] = 5.0

    report = evaluate_divergence(read_solid_residuals(_log(tmp_path / "Solid.log", values)))

    assert report.verdict == "inconclusive"
    assert report.active_fraction < 0.5
    assert "activation floor" in report.reason


def test_a_truncated_series_is_inconclusive_not_clean(tmp_path: Path) -> None:
    """A gap means the maxima are lower bounds, so 'no prong fired' proves nothing."""
    values = _flat(1, 400, 5.0)
    for w in range(200, 260):
        del values[w]

    report = evaluate_divergence(read_solid_residuals(_log(tmp_path / "Solid.log", values)))

    assert report.verdict == "inconclusive"
    assert not report.contiguous
    assert "not contiguous" in report.reason


def test_polling_a_live_run_drops_the_window_being_written(tmp_path: Path) -> None:
    """V4: a poll can catch a window mid-write, and half a parity is not a measurement."""
    values = _flat(1, GRID_START_WINDOW + 39, 5.0)
    values[GRID_START_WINDOW + 39] = 5.0 * 1e6  # the half-written window

    series = read_solid_residuals(_log(tmp_path / "Solid.log", values))
    live = evaluate_divergence(series, exclude_last_window=True)
    naive = evaluate_divergence(series)

    assert live.complete_chunks == naive.complete_chunks - 1
    assert live.worst_parity_ratio == pytest.approx(1.0)


def test_startup_windows_are_outside_the_grid(tmp_path: Path) -> None:
    """Windows 1-100 are never evaluated: healthy growth across that boundary reaches 3.9x."""
    values = _flat(1, 200, 5.0)
    for w in range(1, GRID_START_WINDOW, 2):
        values[w] = 5.0 * 100.0

    report = evaluate_divergence(read_solid_residuals(_log(tmp_path / "Solid.log", values)))

    assert report.verdict == "clean"
    assert report.evaluated_windows == (GRID_START_WINDOW, GRID_START_WINDOW + 99)


def test_too_short_to_evaluate_says_so(tmp_path: Path) -> None:
    report = evaluate_divergence(
        read_solid_residuals(_log(tmp_path / "Solid.log", _flat(1, 110, 5.0)))
    )
    assert report.verdict == "no-data"
    assert report.complete_chunks == 0


def test_solid_log_path_is_the_case_root(tmp_path: Path) -> None:
    assert solid_log_path(tmp_path) == tmp_path / "Solid.log"

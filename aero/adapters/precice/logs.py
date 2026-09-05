"""Readers for preCICE coupling logs, and the fail-loud coupling-convergence gate.

An implicit coupling scheme sub-iterates each time window until its convergence
measures are met, or until ``max-iterations`` is reached. **Hitting the cap is not a
converged window** — preCICE proceeds anyway, and the solve carries on producing
plausible-looking numbers. Turek-Hron FSI3 is the highest-added-mass tutorial case, so
this is the realistic failure mode, and a displacement amplitude read off a run with
non-converged windows is not reportable no matter how close to the published band it
lands.

:func:`assert_coupling_converged` is therefore called from
``PreciceCoupledSolver.load()`` — the same fail-loud placement the moving-mesh adapter
uses for its periodic-steady-state check — so no V&V path can reach a verdict without
passing it (ADR-036 gate K1).

Written by ``BaseCouplingScheme`` (verified against preCICE v3.4.1 source):

* ``precice-<Participant>-iterations.log`` — columns
  ``TimeWindow  TotalIterations  Iterations  Convergence`` (all integers;
  ``Convergence`` is 1/0). The participant that runs the quasi-Newton acceleration
  appends ``QNColumns  DeletedQNColumns  DroppedQNColumns``; its peer does not. Those
  extra columns are the IQN-ILS filter behaviour that gate K3 records as a diagnostic,
  so they are read when present and never required.
* ``precice-<Participant>-convergence.log`` — per-iteration residuals; written only by
  the participant that is *not* first in the scheme. Diagnostic only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aero.adapters.precice._txt_table import TxtTableError, read_txt_table

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

_ITERATIONS_COLUMNS = ("TimeWindow", "TotalIterations", "Iterations", "Convergence")


class CouplingConvergenceError(RuntimeError):
    """The coupling did not converge; the run is not reportable."""


class TimeWindowIterations(BaseModel):
    """One row of an iterations log."""

    model_config = _STRICT

    time_window: int = Field(..., ge=0)
    total_iterations: int = Field(..., ge=0)
    iterations: int = Field(..., ge=0)
    converged: bool


class CouplingIterationReport(BaseModel):
    """Per-window coupling iteration counts for one participant."""

    model_config = _STRICT

    path: Path
    participant: str = Field(..., min_length=1)
    max_iterations_configured: int = Field(..., ge=1)
    windows: tuple[TimeWindowIterations, ...] = Field(..., min_length=1)
    n_dropped: int = Field(default=0, ge=0)
    quasi_newton_columns: tuple[str, ...] = Field(
        default=(),
        description="Extra IQN-ILS diagnostic columns present, if this participant ran it.",
    )

    @model_validator(mode="after")
    def _iterations_within_cap(self) -> CouplingIterationReport:
        over = [
            w.time_window for w in self.windows if w.iterations > self.max_iterations_configured
        ]
        if over:
            raise ValueError(
                f"{self.path}: time window(s) {over[:5]} report more iterations than the "
                f"configured cap {self.max_iterations_configured} — the log and the "
                "configuration disagree; one of them is not from this run"
            )
        return self

    @property
    def n_windows(self) -> int:
        return len(self.windows)

    @property
    def nonconverged(self) -> tuple[TimeWindowIterations, ...]:
        """Windows that did not converge — either flagged, or capped out.

        Both conditions are checked: `Convergence == 0` is preCICE's own verdict, and
        `iterations == max-iterations` catches the case where the cap was reached.
        """
        return tuple(
            w
            for w in self.windows
            if not w.converged or w.iterations >= self.max_iterations_configured
        )

    @property
    def n_nonconverged(self) -> int:
        return len(self.nonconverged)

    @property
    def all_converged(self) -> bool:
        return self.n_nonconverged == 0

    @property
    def max_observed_iterations(self) -> int:
        return max(w.iterations for w in self.windows)

    @property
    def mean_iterations(self) -> float:
        return sum(w.iterations for w in self.windows) / len(self.windows)

    @property
    def iterations_per_window(self) -> tuple[int, ...]:
        """Iterations each window took, in window order.

        The record any per-iteration output file has to be reconciled against: under
        implicit coupling a function object re-executes once per iteration, so the number
        of repeated times in its output is ``sum(iterations) - n_windows`` exactly. Both
        the CalculiX ``.dat`` reader and the fluid force reader classify their cadence
        against this rather than assuming one.
        """
        return tuple(w.iterations for w in self.windows)

    @property
    def total_iterations(self) -> int:
        return sum(w.iterations for w in self.windows)

    def within(self, *, first_window: int, last_window: int) -> CouplingIterationReport:
        """The sub-report covering ``first_window <= TimeWindow <= last_window``.

        The gate is applied to the ANALYSIS window, not the whole run: the start-up
        transient legitimately needs many iterations (upstream documents this), and a
        capped window at t = 0.01 s says nothing about a limit cycle measured at t > 4 s.
        """
        selected = tuple(w for w in self.windows if first_window <= w.time_window <= last_window)
        if not selected:
            raise CouplingConvergenceError(
                f"{self.path}: no time windows in [{first_window}, {last_window}] — "
                f"the log covers [{self.windows[0].time_window}, "
                f"{self.windows[-1].time_window}]"
            )
        return self.model_copy(update={"windows": selected})


def iterations_log_path(case_root: Path, participant_dir: str, participant: str) -> Path:
    return case_root / participant_dir / f"precice-{participant}-iterations.log"


def read_iterations_log(
    path: Path, *, participant: str, max_iterations_configured: int
) -> CouplingIterationReport:
    """Parse ``precice-<Participant>-iterations.log``."""
    try:
        table = read_txt_table(path, required_prefix=_ITERATIONS_COLUMNS)
    except TxtTableError as exc:
        raise CouplingConvergenceError(str(exc)) from exc
    if table.n_rows == 0:
        raise CouplingConvergenceError(
            f"{path}: header only — the coupling completed no time windows"
        )
    windows = tuple(
        TimeWindowIterations(
            time_window=int(row[0]),
            total_iterations=int(row[1]),
            iterations=int(row[2]),
            converged=int(row[3]) == 1,
        )
        for row in table.rows
    )
    return CouplingIterationReport(
        path=path,
        participant=participant,
        max_iterations_configured=max_iterations_configured,
        windows=windows,
        n_dropped=table.n_dropped,
        quasi_newton_columns=table.columns[len(_ITERATIONS_COLUMNS) :],
    )


def assert_coupling_converged(report: CouplingIterationReport) -> None:
    """Raise unless EVERY time window in `report` converged (ADR-036 gate K1).

    Never relax this. A window that exhausted `max-iterations` has an unconverged
    fluid-structure equilibrium; the resulting displacement is not a solution of the
    coupled problem, and its agreement with a published band would be coincidence.
    """
    bad = report.nonconverged
    if not bad:
        return
    shown = ", ".join(
        f"window {w.time_window} ({w.iterations} iters, "
        f"{'flagged non-converged' if not w.converged else 'hit the cap'})"
        for w in bad[:5]
    )
    more = "" if len(bad) <= 5 else f" (+{len(bad) - 5} more)"
    raise CouplingConvergenceError(
        f"{report.path}: {len(bad)} of {report.n_windows} time windows did not converge "
        f"under max-iterations={report.max_iterations_configured}: {shown}{more}. "
        "A non-converged coupled solve is NOT reportable — investigate the coupling "
        "(added mass, acceleration, time-window size); do not relax the gate."
    )


class ConvergenceTrace(BaseModel):
    """Per-iteration residuals from ``precice-<Participant>-convergence.log`` (diagnostic)."""

    model_config = _STRICT

    path: Path
    columns: tuple[str, ...] = Field(..., min_length=2)
    rows: tuple[tuple[float, ...], ...] = Field(..., min_length=1)


def read_convergence_log(path: Path) -> ConvergenceTrace:
    """Parse a convergence log. Diagnostic only — never gated."""
    table = read_txt_table(path)
    return ConvergenceTrace(
        path=path,
        columns=table.columns,
        rows=tuple(tuple(float(v) for v in row) for row in table.rows),
    )


def find_iterations_logs(case_root: Path) -> dict[str, Path]:
    """Locate every ``precice-*-iterations.log`` under `case_root`, keyed by participant.

    Globbed rather than constructed: which participants write an iterations log depends
    on the scheme, so requiring a specific one would be brittle. Finding *none* is a
    loud failure — it means the coupling never started.
    """
    found: dict[str, Path] = {}
    for path in sorted(case_root.rglob("precice-*-iterations.log")):
        participant = path.name[len("precice-") : -len("-iterations.log")]
        found[participant] = path
    if not found:
        raise CouplingConvergenceError(
            f"{case_root}: no precice-*-iterations.log anywhere. The coupling produced no "
            "iteration record — the participants never connected, or never completed a "
            "time window."
        )
    return found


# --------------------------------------------------------------------------------------
# ADR-041 V2/V4 — the solid-side parity divergence detector
#
# The flexible arm's N3 attempt-1 abort had a ~150-window precursor that every
# interface-side series missed: a period-2, odd-window instability inside CalculiX
# (handoff 6.49). This is the pre-registered detector for it, and it is deliberately NOT
# an absolute-newton threshold -- the healthy residual envelope tracks the commanded load
# (0.65 -> 24.49 N over the first 1500 windows of a run whose full amplitude is another
# 464x beyond that), so any fixed threshold either fires on healthy full-amplitude
# operation or stays silent through a divergence. What separates sick from healthy is
# PARITY, and both prongs below are ratios of like quantities, which is what makes them
# meaningful at any amplitude.
#
# The input is `Solid.log`, and ONLY `Solid.log`: ccx's `.cvg` RESID.FORCE column is a
# PERCENTAGE normalised by a near-zero early-ramp average force, so it cannot be compared
# across windows. The extraction reproduces session 12's `minerB_parse.awk` (sha256
# 0d6eeca9934632a9fc278db9e59f13aba56e1c1a132cf00a042abd67b3f35a2c), which is the
# reference the tests check this implementation against.
# --------------------------------------------------------------------------------------

#: Grid origin. Windows 1-100 are startup and are never evaluated: across the w1-100
#: boundary healthy growth reaches 3.1x (flexible) and 3.9x (rigid), which is startup
#: settling rather than divergence.
GRID_START_WINDOW = 101
CHUNK_WINDOWS = 20
BLOCK_WINDOWS = 100
#: Both parities must reach this before a chunk or block is compared. Below it these are
#: ratios of near-zero residuals, where a large ratio carries no information.
ACTIVATION_FLOOR_N = 1.0
#: Parity prong. No healthy chunk in any measured dataset reaches this even once: worst
#: observed is 2.45 (rigid arm, complete 76 090-window full-amplitude run), 1.81
#: (flexible healthy w101-1540), 1.53 (Q1 control).
PARITY_RATIO_LIMIT = 4.0
#: ...and it must hold over this many GRID-adjacent active chunks. Requiring two rather
#: than one is deliberate: under ADR-041 V1 a single-chunk artefact would otherwise
#: permanently fail a rung.
PARITY_CONSECUTIVE_CHUNKS = 2
#: Runaway prong (the parity-symmetric backstop). Worst healthy same-parity block growth
#: is 1.75x (flexible), 1.70x (Q1), 1.17x (rigid); the dying arm's odd blocks jump 32.0x.
BLOCK_GROWTH_LIMIT = 3.0
#: Below this share of active chunks the detector is inert rather than discriminating,
#: and says so instead of reporting health (ADR-041 V2 (iii)).
MIN_ACTIVE_FRACTION = 0.5

_WINDOW_MARKER_RE = re.compile(r"time-window\s+(\d+)")
_RESIDUAL_RE = re.compile(r"largest residual force=\s*(-?[0-9]+(?:\.[0-9]*)?(?:[eE][-+]?[0-9]+)?)")
_ARGMAX_NODE_RE = re.compile(r"in node\s+(\d+)")
_NO_CONVERGENCE_RE = re.compile(r"no convergence")


class SolidLogError(RuntimeError):
    """`Solid.log` is missing, unreadable, or carries no window at all."""


class SolidResidualWindow(BaseModel):
    """One coupling window's solid-side residual census."""

    model_config = _STRICT

    window: int = Field(..., ge=1)
    max_abs_residual: float = Field(..., ge=0.0)
    argmax_node: int | None = None
    n_residuals: int = Field(..., ge=0)
    n_no_convergence: int = Field(..., ge=0)


class SolidResidualSeries(BaseModel):
    """Per-window maxima extracted from one `Solid.log`."""

    model_config = _STRICT

    path: Path
    windows: tuple[SolidResidualWindow, ...] = Field(..., min_length=1)

    @property
    def first_window(self) -> int:
        return self.windows[0].window

    @property
    def last_window(self) -> int:
        return self.windows[-1].window

    @property
    def is_contiguous(self) -> bool:
        """Every window between the first and the last is present, exactly once.

        A gap means the log was rotated or truncated, and a maximum read off it is a
        lower bound rather than a measurement -- ADR-041 V2 (ii) makes that INCONCLUSIVE
        rather than clean.
        """
        seen = [w.window for w in self.windows]
        return seen == list(range(seen[0], seen[-1] + 1))

    def by_window(self) -> dict[int, float]:
        return {w.window: w.max_abs_residual for w in self.windows}


class DivergenceFinding(BaseModel):
    """One prong firing, with the evidence that fired it."""

    model_config = _STRICT

    prong: Literal["parity", "runaway"]
    fired_at_window: int = Field(..., ge=1)
    value: float
    limit: float
    detail: str


class DivergenceReport(BaseModel):
    """The ADR-041 V2 verdict over one series."""

    model_config = _STRICT

    verdict: Literal["precursor", "clean", "inconclusive", "no-data"]
    findings: tuple[DivergenceFinding, ...] = ()
    n_windows: int = Field(..., ge=0)
    evaluated_windows: tuple[int, int] | None = None
    complete_chunks: int = Field(..., ge=0)
    active_chunks: int = Field(..., ge=0)
    active_fraction: float = Field(..., ge=0.0, le=1.0)
    worst_parity_ratio: float | None = None
    worst_parity_chunk: tuple[int, int] | None = None
    worst_block_growth: float | None = None
    contiguous: bool = True
    reason: str

    @property
    def fired(self) -> bool:
        return self.verdict == "precursor"

    def one_line(self) -> str:
        ratio = "n/a" if self.worst_parity_ratio is None else f"{self.worst_parity_ratio:.2f}"
        growth = "n/a" if self.worst_block_growth is None else f"{self.worst_block_growth:.2f}"
        return (
            f"ADR-041 detector: {self.verdict.upper()} — worst parity ratio {ratio} "
            f"(limit {PARITY_RATIO_LIMIT} over {PARITY_CONSECUTIVE_CHUNKS} chunks), "
            f"worst block growth {growth} (limit {BLOCK_GROWTH_LIMIT}), "
            f"{self.active_chunks}/{self.complete_chunks} chunks active. {self.reason}"
        )


def solid_log_path(case_root: Path) -> Path:
    return case_root / "Solid.log"


def read_solid_residuals(path: Path) -> SolidResidualSeries:
    """Extract per-window solid residual maxima from `Solid.log`.

    Lines are attributed to the last-seen ``time-window N`` marker, exactly as session
    12's `minerB_parse.awk` does. Those marker lines carry ANSI escape bytes, so this
    matches with a regex and never splits on fixed fields; the file is read with
    ``errors="replace"`` because a live log can be caught mid-write.
    """
    if not path.exists():
        raise SolidLogError(f"{path}: no Solid.log — the solid participant never started")
    window = 0
    max_abs: dict[int, float] = {}
    node: dict[int, int | None] = {}
    n_res: dict[int, int] = {}
    n_noconv: dict[int, int] = {}
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            marker = _WINDOW_MARKER_RE.search(line)
            if marker is not None:
                window = int(marker.group(1))
                max_abs.setdefault(window, 0.0)
                node.setdefault(window, None)
                n_res.setdefault(window, 0)
                n_noconv.setdefault(window, 0)
                continue
            if window == 0:
                continue
            residual = _RESIDUAL_RE.search(line)
            if residual is not None:
                value = abs(float(residual.group(1)))
                n_res[window] += 1
                if value > max_abs[window]:
                    max_abs[window] = value
                    found = _ARGMAX_NODE_RE.search(line)
                    node[window] = int(found.group(1)) if found is not None else None
                continue
            if _NO_CONVERGENCE_RE.search(line):
                n_noconv[window] += 1
    if not max_abs:
        raise SolidLogError(
            f"{path}: no 'time-window' marker anywhere — the coupling never advanced a "
            "window, so there is nothing to evaluate"
        )
    windows = tuple(
        SolidResidualWindow(
            window=w,
            max_abs_residual=max_abs[w],
            argmax_node=node[w],
            n_residuals=n_res[w],
            n_no_convergence=n_noconv[w],
        )
        for w in sorted(max_abs)
    )
    return SolidResidualSeries(path=path, windows=windows)


def _units(
    values: dict[int, float], *, size: int, last_window: int
) -> list[tuple[int, int, float | None, float | None]]:
    """Complete grid units from GRID_START_WINDOW: (start, end, odd max, even max)."""
    out: list[tuple[int, int, float | None, float | None]] = []
    start = GRID_START_WINDOW
    while start + size - 1 <= last_window:
        end = start + size - 1
        odd = [values[w] for w in range(start, end + 1) if w in values and w % 2 == 1]
        even = [values[w] for w in range(start, end + 1) if w in values and w % 2 == 0]
        if len(odd) + len(even) == size:
            out.append((start, end, max(odd) if odd else None, max(even) if even else None))
        start += size
    return out


def _is_active(odd: float | None, even: float | None) -> bool:
    return odd is not None and even is not None and min(odd, even) >= ACTIVATION_FLOOR_N


def evaluate_divergence(
    series: SolidResidualSeries, *, exclude_last_window: bool = False
) -> DivergenceReport:
    """Apply ADR-041 V2's two prongs to `series`.

    `exclude_last_window` is for polling a LIVE run (V4): the highest-numbered window may
    be caught mid-write, and half of a parity is not a measurement. Complete units only,
    never a trailing partial one.
    """
    values = series.by_window()
    if exclude_last_window and values:
        values.pop(max(values), None)
    contiguous = series.is_contiguous
    if not values or max(values) < GRID_START_WINDOW + CHUNK_WINDOWS - 1:
        return DivergenceReport(
            verdict="no-data",
            n_windows=len(values),
            complete_chunks=0,
            active_chunks=0,
            active_fraction=0.0,
            contiguous=contiguous,
            reason=(
                f"fewer than one complete chunk past window {GRID_START_WINDOW} — "
                "nothing to evaluate yet"
            ),
        )
    last = max(values)
    chunks = _units(values, size=CHUNK_WINDOWS, last_window=last)
    blocks = _units(values, size=BLOCK_WINDOWS, last_window=last)

    findings: list[DivergenceFinding] = []
    worst_ratio: float | None = None
    worst_chunk: tuple[int, int] | None = None
    run = 0
    for start, end, odd, even in chunks:
        if not _is_active(odd, even):
            run = 0  # an inactive chunk BREAKS the pair; inactive chunks are never skipped
            continue
        assert odd is not None and even is not None
        ratio = max(odd, even) / min(odd, even)
        if worst_ratio is None or ratio > worst_ratio:
            worst_ratio, worst_chunk = ratio, (start, end)
        if ratio >= PARITY_RATIO_LIMIT:
            run += 1
            if run >= PARITY_CONSECUTIVE_CHUNKS and not findings:
                findings.append(
                    DivergenceFinding(
                        prong="parity",
                        fired_at_window=end,
                        value=ratio,
                        limit=PARITY_RATIO_LIMIT,
                        detail=(
                            f"{PARITY_CONSECUTIVE_CHUNKS} consecutive active chunks at "
                            f"odd/even ratio >= {PARITY_RATIO_LIMIT}; chunk w{start}-{end} "
                            f"is {ratio:.2f} (odd {odd:.3f} N, even {even:.3f} N)"
                        ),
                    )
                )
        else:
            run = 0

    worst_growth: float | None = None
    for index in range(1, len(blocks)):
        start, end, odd, even = blocks[index]
        p_start, p_end, p_odd, p_even = blocks[index - 1]
        if not _is_active(odd, even) or not _is_active(p_odd, p_even):
            continue  # no comparison for this pair; growth never accumulates across a gap
        for name, current, previous in (("odd", odd, p_odd), ("even", even, p_even)):
            assert current is not None and previous is not None
            growth = current / previous
            if worst_growth is None or growth > worst_growth:
                worst_growth = growth
            if growth >= BLOCK_GROWTH_LIMIT:
                findings.append(
                    DivergenceFinding(
                        prong="runaway",
                        fired_at_window=end,
                        value=growth,
                        limit=BLOCK_GROWTH_LIMIT,
                        detail=(
                            f"{name} block max grew {growth:.2f}x over the preceding grid "
                            f"block ({previous:.3f} -> {current:.3f} N, w{p_start}-{p_end} "
                            f"-> w{start}-{end})"
                        ),
                    )
                )
    active = sum(1 for _, _, odd, even in chunks if _is_active(odd, even))
    fraction = active / len(chunks) if chunks else 0.0

    if findings:
        verdict: Literal["precursor", "clean", "inconclusive", "no-data"] = "precursor"
        reason = findings[0].detail
    elif not contiguous:
        verdict = "inconclusive"
        reason = (
            f"the series is not contiguous over w{series.first_window}-{series.last_window} "
            "— a truncated or rotated log under-reports maxima (V2 (ii))"
        )
    elif fraction < MIN_ACTIVE_FRACTION:
        verdict = "inconclusive"
        reason = (
            f"only {fraction:.1%} of chunks reach the {ACTIVATION_FLOOR_N} N activation "
            f"floor (V2 (iii) requires {MIN_ACTIVE_FRACTION:.0%}) — the detector is inert "
            "here, which is not the same as health"
        )
    else:
        verdict = "clean"
        reason = "neither prong fired over the evaluated span"
    return DivergenceReport(
        verdict=verdict,
        findings=tuple(findings),
        n_windows=len(values),
        evaluated_windows=(GRID_START_WINDOW, chunks[-1][1]) if chunks else None,
        complete_chunks=len(chunks),
        active_chunks=active,
        active_fraction=fraction,
        worst_parity_ratio=worst_ratio,
        worst_parity_chunk=worst_chunk,
        worst_block_growth=worst_growth,
        contiguous=contiguous,
        reason=reason,
    )

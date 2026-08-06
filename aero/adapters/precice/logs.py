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

from pathlib import Path

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

"""Read pimpleFoam's per-step Courant lines and cost structure out of a participant log.

Two readers, one log, one parsing idiom.

``read_courant_history`` is gate I7's input. pimpleFoam prints ``Courant Number mean: <m>
max: <M>`` once per time step regardless of ``adjustTimeStep``. Under IMPLICIT coupling the
preCICE adapter rewinds ``runTime`` and the solver re-prints the step, so both ``Time =``
and Courant lines repeat per coupling iteration; every Courant line here is therefore
paired with the MOST RECENT ``Time =`` line above it, and a maximum over any window is
repeat-insensitive (the re-done step prints the same converged-state Courant or a smaller
provisional one — never a larger one that the physics did not produce; I7 gates the
maximum, so extra repeats can only be conservative).

``read_fluid_cost_history`` is where a wave's wall clock actually goes. ``ExecutionTime``
is the participant process's cumulative CPU and ``ClockTime`` its cumulative wall, both
printed once per fluid time-step solve; their difference is every second the process spent
NOT computing — NFS writes, preCICE exchange, waiting on the solid. Differencing the
cumulative pair gives a per-step cost, and the ``Solving for <field>`` lines in between
give the linear-solver work that cost bought. That pairing is what makes the I/O and
coupling-overhead hypotheses *falsifiable* from a run that has already happened, rather
than a decomposition to be argued about.

Both readers interleave their regexes BY BYTE OFFSET rather than scanning line kinds
separately: under implicit coupling the same ``Time =`` value appears many times, so
"the last time seen" is the only correct attribution and it requires one ordered pass.

Stdlib + numpy + pydantic only (Invariant 1). The precedent for reading a participant
log is ``flexible_foil.read_interface_power``.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "CourantHistory",
    "FluidCostHistory",
    "FluidStepCost",
    "SolverLogError",
    "read_courant_history",
    "read_fluid_cost_history",
]

_TIME_LINE = re.compile(r"^Time = (?P<time>[0-9eE+.\-]+)\s*$", re.MULTILINE)
_COURANT_LINE = re.compile(
    r"^Courant Number mean: (?P<mean>[0-9eE+.\-]+) max: (?P<max>[0-9eE+.\-]+)\s*$",
    re.MULTILINE,
)
_EXEC_LINE = re.compile(
    r"^ExecutionTime = (?P<cpu>[0-9eE+.\-]+) s\s+ClockTime = (?P<wall>[0-9eE+.\-]+) s\s*$",
    re.MULTILINE,
)
_SOLVE_LINE = re.compile(
    r"^(?P<solver>[A-Za-z][A-Za-z0-9]*):\s+Solving for (?P<field>\w+), "
    r"Initial residual = (?P<initial>[0-9eE+.\-]+), "
    r"Final residual = (?P<final>[0-9eE+.\-]+), "
    r"No Iterations (?P<iterations>\d+)\s*$",
    re.MULTILINE,
)


class SolverLogError(Exception):
    """The log does not carry what the probe needs; the reason is the message."""


class CourantHistory(BaseModel):
    """Every Courant line, paired with the ``Time =`` it was printed under."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    t: tuple[float, ...] = Field(..., min_length=1)
    mean: tuple[float, ...] = Field(..., min_length=1)
    max: tuple[float, ...] = Field(..., min_length=1)
    n_lines: int = Field(..., ge=1, description="Courant lines read, repeats included.")

    def max_over(self, *, t_start: float) -> float:
        """The maximum Courant number at or after ``t_start`` — I7's measured quantity."""
        t = np.asarray(self.t, dtype=np.float64)
        window: NDArray[np.bool_] = t >= t_start
        if not bool(window.any()):
            raise SolverLogError(
                f"no Courant line at or after t = {t_start!r}: the log ends at "
                f"t = {max(self.t)!r}, so the probe never reached the window it was "
                "meant to measure — the maximum would describe the ramp, not the "
                "post-ramp regime"
            )
        return float(np.asarray(self.max, dtype=np.float64)[window].max())


def read_courant_history(log_path: Path) -> CourantHistory:
    """Parse the fluid participant's log; every Courant line keeps its printed time."""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SolverLogError(f"cannot read {log_path}: {exc}") from exc

    events: list[tuple[float, float, float]] = []
    current_time: float | None = None
    matches = sorted(
        [(m.start(), "time", m) for m in _TIME_LINE.finditer(text)]
        + [(m.start(), "courant", m) for m in _COURANT_LINE.finditer(text)],
        key=lambda item: item[0],
    )
    for _, kind, match in matches:
        if kind == "time":
            current_time = float(match.group("time"))
        else:
            if current_time is None:
                # OpenFOAM prints the very first Courant line BEFORE the first
                # "Time =" (the t=0 state during initialisation); attribute it to 0.
                current_time = 0.0
            events.append((current_time, float(match.group("mean")), float(match.group("max"))))

    if not events:
        raise SolverLogError(
            f"{log_path} carries no 'Courant Number mean: ... max: ...' lines — either "
            "the solve never took a step or this is not a pimpleFoam participant log"
        )
    return CourantHistory(
        t=tuple(e[0] for e in events),
        mean=tuple(e[1] for e in events),
        max=tuple(e[2] for e in events),
        n_lines=len(events),
    )


class FluidStepCost(BaseModel):
    """One fluid time-step solve: what it cost, and the linear-solver work it bought.

    Under implicit coupling one *step* is one coupling ITERATION — the adapter rewinds
    ``runTime`` and the solver re-solves the same physical time. ``t`` therefore repeats
    across steps, and a rate must be taken per step, never per distinct ``t``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    t: float = Field(..., description="The 'Time =' this step was solved at; repeats.")
    execution_time_s: float = Field(..., ge=0.0, description="Cumulative process CPU.")
    clock_time_s: float = Field(..., ge=0.0, description="Cumulative process wall clock.")
    d_execution_s: float = Field(..., description="CPU spent since the previous step.")
    d_clock_s: float = Field(..., description="Wall spent since the previous step.")
    iterations_by_field: dict[str, int] = Field(
        ..., description="Summed linear-solver iterations per field within this step."
    )
    solves_by_field: dict[str, int] = Field(
        ...,
        description=(
            "How many times each field was solved within this step. Distinct from the "
            "iteration count: 8 pressure solves of 100 iterations and 1 of 800 cost "
            "about the same but say different things about the discretisation."
        ),
    )
    solver_by_field: dict[str, str] = Field(
        ..., description="The solver name OpenFOAM printed per field (GAMG, PCG, ...)."
    )


class FluidCostHistory(BaseModel):
    """Every fluid step-solve in one participant log, in the order the solver ran them."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    steps: tuple[FluidStepCost, ...] = Field(..., min_length=1)
    log_path: str = Field(..., min_length=1)

    @property
    def n_steps(self) -> int:
        return len(self.steps)

    @property
    def total_execution_s(self) -> float:
        """Cumulative CPU at the last step — the process's own accounting, not a sum."""
        return self.steps[-1].execution_time_s

    @property
    def total_clock_s(self) -> float:
        return self.steps[-1].clock_time_s

    @property
    def cpu_fraction_of_wall(self) -> float:
        """CPU ÷ wall over the whole run.

        ``1 - cpu_fraction_of_wall`` is a HARD upper bound on everything the fluid process
        was not computing: NFS writes, preCICE exchange, and waiting for the solid. Any
        lever that attacks only those cannot beat it. It is a bound at the rate that was
        MEASURED, though — halve the compute and the same absolute seconds are twice the
        share, so it must be re-read at every rung of a speed-up ladder.
        """
        if self.total_clock_s <= 0.0:
            raise SolverLogError(
                f"{self.log_path}: the final ClockTime is {self.total_clock_s!r}, so no "
                "wall-clock fraction exists — the log was truncated before the solve ran"
            )
        return self.total_execution_s / self.total_clock_s

    @property
    def mean_seconds_per_step(self) -> float:
        return float(np.mean([s.d_execution_s for s in self.steps]))

    def iterations_per_step(self, *fields: str) -> NDArray[np.float64]:
        """Per-step summed iterations over ``fields`` — the cost model's regressor."""
        return np.asarray(
            [float(sum(s.iterations_by_field.get(f, 0) for f in fields)) for s in self.steps],
            dtype=np.float64,
        )

    def d_execution(self) -> NDArray[np.float64]:
        return np.asarray([s.d_execution_s for s in self.steps], dtype=np.float64)

    def fields(self) -> tuple[str, ...]:
        """Every field solved anywhere in the log, sorted — the regressor vocabulary."""
        seen: set[str] = set()
        for step in self.steps:
            seen.update(step.iterations_by_field)
        return tuple(sorted(seen))


def read_fluid_cost_history(log_path: Path) -> FluidCostHistory:
    """Parse per-step CPU/wall and the linear-solver work inside each step.

    An ``ExecutionTime`` line CLOSES a step: everything parsed since the previous one
    belongs to it. That is the only attribution that survives implicit coupling, where the
    function objects and the preCICE exchange print AFTER the ``ExecutionTime`` line of the
    step whose cost they are part of — their cost lands in the next step's delta, which is
    why the intercept of a per-step regression, not the solve lines alone, is what bounds
    the non-solver share.
    """
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SolverLogError(f"cannot read {log_path}: {exc}") from exc

    steps: list[FluidStepCost] = []
    current_time = 0.0
    iterations: dict[str, int] = {}
    solves: dict[str, int] = {}
    solvers: dict[str, str] = {}
    previous_cpu = 0.0
    previous_wall = 0.0

    matches = sorted(
        [(m.start(), "time", m) for m in _TIME_LINE.finditer(text)]
        + [(m.start(), "solve", m) for m in _SOLVE_LINE.finditer(text)]
        + [(m.start(), "exec", m) for m in _EXEC_LINE.finditer(text)],
        key=lambda item: item[0],
    )
    for _, kind, match in matches:
        if kind == "time":
            current_time = float(match.group("time"))
        elif kind == "solve":
            field = match.group("field")
            iterations[field] = iterations.get(field, 0) + int(match.group("iterations"))
            solves[field] = solves.get(field, 0) + 1
            solvers[field] = match.group("solver")
        else:
            cpu = float(match.group("cpu"))
            wall = float(match.group("wall"))
            if cpu < previous_cpu or wall < previous_wall:
                raise SolverLogError(
                    f"{log_path}: ExecutionTime went backwards ({previous_cpu} -> {cpu} s) "
                    f"at step {len(steps) + 1}. Cumulative counters only decrease when two "
                    "runs were appended to one log; every per-step delta after the seam "
                    "would be wrong, and one of them would be hugely negative"
                )
            steps.append(
                FluidStepCost(
                    t=current_time,
                    execution_time_s=cpu,
                    clock_time_s=wall,
                    d_execution_s=cpu - previous_cpu,
                    d_clock_s=wall - previous_wall,
                    iterations_by_field=dict(sorted(iterations.items())),
                    solves_by_field=dict(sorted(solves.items())),
                    solver_by_field=dict(sorted(solvers.items())),
                )
            )
            previous_cpu, previous_wall = cpu, wall
            iterations, solves, solvers = {}, {}, {}

    if not steps:
        raise SolverLogError(
            f"{log_path} carries no 'ExecutionTime = ... ClockTime = ...' lines — either "
            "the solve never completed a time step or this is not an OpenFOAM solver log"
        )
    return FluidCostHistory(steps=tuple(steps), log_path=str(log_path))

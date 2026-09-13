"""Measure one arm of the Heathcote-Gursul flexible-foil campaign, and pair two of them.

The only module in the platform that imports both adapters. That direction is deliberate
and one-way: ``aero/vv/`` may reach into ``aero/adapters/``, never the reverse, which is why
the fluid's force history is read here rather than inside ``PreciceCoupledSolver.load()``.

**The gates cannot be skipped, structurally.** :func:`read_arm` calls ``solver.load(result)``
FIRST and takes its analysis window from the returned ``SolveResult``. ``load`` is where K2
(the run ended reportably), C4 (the watch-point header matches the configuration) and K1
(every coupling window inside the analysis window converged) are enforced, and this module
has no other source for the window every statistic must be confined to: it cannot widen it,
and it cannot obtain it without paying for the gates.

What is measured, and why each one exists:

* ``C_T`` -- thrust, from the dimensional ``force.dat``. The gated quantity (D1).
* ``C_P`` -- the rate at which the fluid does work on the structure, from the coded
  interface-power object (P2). **This is the C_P of record.** The plate DEFORMS, so there is
  no single rigid-body wall velocity and the naive product is an approximation.
* ``C_P1`` -- that naive product, computed from the PRESCRIBED plunge velocity and reported
  as the bias the naive formula would have injected (D9, reported-only, on BOTH arms). It is
  emphatically NOT routed through ``propulsive_metrics``: ``MotionKinematics.velocity`` is
  ``A w cos(wt)`` while the solid's plunge velocity is ``-a w sin(wt)`` post-ramp -- exactly
  90 degrees out of phase, which turns the power integral into a quadrature and makes
  ``C_P`` come out near zero while looking entirely reasonable.
* ``P3`` -- the reaction power at the prescribed nodes, from the CalculiX ``.dat``. With
  ``ALPHA = 0`` and no damping the solid's energy balance gives ``<RF . v> = <P2>`` exactly
  over a cycle, so ``(P3 - P2) / P2`` is a genuine closure identity (D10) rather than a
  restatement of something already known.
* ``eta = <C_T> / <C_P>`` -- a **ratio of means, never a mean of ratios** (D2).

Signs are derived, never repaired. Nothing here calls ``abs()``: a sign slip makes D10 read
about 200 %, which is loud, and D7's admissibility check on the SIGNED efficiency catches a
sign error in P2. Quietly correcting one would convert a loud failure into a plausible
number, which is the class of thing this stage exists to prevent.

stdlib + numpy + pydantic only.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from aero.adapters._base import ResultHandle, SolveResult
from aero.adapters.openfoam.flexible_foil import InterfacePowerHistory, read_interface_power
from aero.adapters.openfoam.force_io import (
    ForceHistory,
    classify_repeat_cadence,
    read_force_history,
)
from aero.adapters.precice.case import AuthoredSource, CoupledCaseSpec
from aero.adapters.precice.ccx_dat import read_reaction_forces
from aero.adapters.precice.schedule import (
    ScheduleError,
    StampConvention,
    common_windows,
    select_windows,
    window_indices,
)
from aero.adapters.precice.solver import PreciceCoupledSolver
from aero.postprocess import LimitCycleAnalysis, analyse_limit_cycle
from aero.vv._base import BenchmarkError
from aero.vv.alignment import per_cycle_efficiency

__all__ = [
    "C_P",
    "C_P1",
    "C_T",
    "D0_DEG",
    "P3",
    "ArmReadout",
    "gated_means",
    "read_arm",
]

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

#: Signal names inside the readout's own limit-cycle analysis.
C_T = "c_t"
C_P = "c_p"
C_P1 = "c_p1"
P3 = "p3"
D0_DEG = "d0_deg"

#: How far the force record's instants may sit from the watch-point's, as a fraction of one
#: coupling window. NOT bitwise: these are two independent ASCII accumulators (OpenFOAM's
#: `forces` object and preCICE's watch-point writer), and `alignment.py` reserves bitwise
#: equality for the cross-ARM comparison of the same file kind, where it is achievable.
#: MEASURED on both surviving I4 arms (see `aero.adapters.precice.schedule`). Declared
#: here as constants rather than inline, so the two conventions are stated in one place
#: and a future participant is added by naming its convention, not by editing arithmetic.
FLUID_STAMP: StampConvention = "window-start"
SOLID_STAMP: StampConvention = "window-end"


class ArmReadout(BaseModel):
    """One arm's measured quantities, over the window ``load()`` derived and gated."""

    model_config = _STRICT

    arm: str = Field(..., min_length=1)
    run_id: str = Field(..., min_length=1)

    # --- the window, taken from the gated solve and never widened ---
    period: float = Field(..., gt=0.0)
    t_start: float
    t_end: float
    n_settled_cycles: int = Field(..., ge=1)
    n_windows: int = Field(..., ge=1)

    # --- gated (D1, D2, D0) ---
    c_t: float = Field(..., description="Cycle-mean thrust coefficient over the window.")
    c_p: float = Field(..., description="Cycle-mean power coefficient, from P2.")
    eta: float = Field(..., description="<C_T> / <C_P> -- a ratio of MEANS.")
    d0_pitch_amplitude_deg: float = Field(..., ge=0.0)

    # --- reported, never gated (D9), and the closure identity (D10) ---
    c_p1: float = Field(..., description="The naive rigid-body power coefficient.")
    p1_p2_bias: float = Field(
        ..., description="(C_P1 - C_P) / C_P -- the bias the naive formula would have injected."
    )
    p3_p2_closure: float = Field(
        ..., description="(P3 - P2) / P2 -- exact under ALPHA=0 with no damping."
    )

    # --- evidence that the record was understood rather than assumed ---
    force_cadence: str = Field(..., min_length=1)
    force_rows_read: int = Field(..., ge=1)
    interface_power_rows_read: int = Field(..., ge=1)
    n_windows_analysed: int = Field(
        ...,
        ge=2,
        description=(
            "Coupling windows every record covered, after the window join. Reported "
            "because it is the length of the series every gated number is built from, "
            "and it is NOT the row count of any one file: the fluid writes one extra "
            "stamp after the last window closes (see precice.schedule)."
        ),
    )
    coupling_mean_iterations: float = Field(..., gt=0.0)

    # --- what the paired path needs ---
    analysis: LimitCycleAnalysis
    force_t: tuple[float, ...] = Field(
        ...,
        min_length=2,
        description=(
            "The ANALYSIS time base -- window-END instants, one per analysed window. "
            "Named force_t for continuity; it is no longer force.dat's raw stamps, which "
            "are window-START and one row longer. A2 compares this bitwise across arms, "
            "and it is derived identically on both, so the comparison still holds."
        ),
    )

    @property
    def c_t_per_cycle(self) -> NDArray[np.float64]:
        return np.asarray(self.analysis.cycles[C_T].per_cycle_mean, dtype=np.float64)

    @property
    def c_p_per_cycle(self) -> NDArray[np.float64]:
        return np.asarray(self.analysis.cycles[C_P].per_cycle_mean, dtype=np.float64)

    @property
    def eta_per_cycle(self) -> NDArray[np.float64]:
        """D4's difference series. Each element is ONE cycle's ratio of means."""
        return per_cycle_efficiency(self.c_t_per_cycle, self.c_p_per_cycle)


def _one_force_file(fluid_dir: Path) -> Path:
    """The single ``force.dat`` this run produced.

    Asserts exactly one match. A re-run into the same case directory leaves a second
    start-time directory beside the first, and silently picking one of them is a plausible
    number out of an ambiguous record -- the failure this whole module is arranged against.
    """
    matches = sorted(fluid_dir.glob("postProcessing/forces1/*/force.dat"))
    if len(matches) != 1:
        raise BenchmarkError(
            f"{fluid_dir}: expected exactly one postProcessing/forces1/*/force.dat, found "
            f"{len(matches)} ({[str(m) for m in matches]}). More than one means the case "
            "directory was run into twice and the record is ambiguous; none means the "
            "forces function object did not run."
        )
    return matches[0]


def gated_means(analysis: LimitCycleAnalysis) -> tuple[float, float, float, float]:
    """The (C_T, C_P, C_P1, P3) means every gated number is built from.

    Each is the SETTLED-TAIL, INTEGER-CYCLE estimator — ``of(name).mean``, the mean over
    full cycles of the per-cycle mean on the re-segmentation anchored at ``t_start``. A
    flat sample mean over ``[t_start, t_end]`` generically spans a fractional trailing
    cycle, and on an oscillating signal that fraction is a phase-dependent bias that
    lands straight in D1, D5 and both legs of the D10 closure ratio (session-7
    adversarial review, candidate 13; candidate 12 is the same error class on eta).
    """
    return (
        analysis.of(C_T).mean,
        analysis.of(C_P).mean,
        analysis.of(C_P1).mean,
        analysis.of(P3).mean,
    )


def read_arm(
    solver: PreciceCoupledSolver,
    result: ResultHandle,
    *,
    arm: str,
) -> ArmReadout:
    """Measure one arm, after -- and only after -- ``load()`` has run every gate.

    The ordering is the point. ``solve`` is obtained first, both because its scalars carry
    the analysis window and because obtaining it is what enforces K2, C4 and K1. There is no
    path from this function to a number that does not go through them.
    """
    solve: SolveResult = solver.load(result)
    spec = result.case_dir.spec
    if not isinstance(spec, CoupledCaseSpec) or not isinstance(spec.source, AuthoredSource):
        raise BenchmarkError(
            f"{arm}: the HG2007 readout drives an authored coupled case; got {type(spec).__name__}"
        )
    source: AuthoredSource = spec.source
    fluid, solid = source.fluid, source.solid

    case_dir = result.output_host_path / spec.case_subdir
    fluid_dir = case_dir / source.fluid_participant_dir
    solid_dir = case_dir / source.solid_participant_dir

    # The coupling's own account of how many times each window was solved. Every
    # per-iteration output file below is reconciled against it rather than de-duplicated
    # on a guess.
    reports = solver.coupling_report(result)
    fluid_report = next((r for r in reports if r.participant == "Fluid"), reports[0])
    solid_report = next((r for r in reports if r.participant == solid.participant), reports[-1])

    # --- the fluid's forces -------------------------------------------------------------
    raw = read_force_history(_one_force_file(fluid_dir), repeats="raw")
    cadence = classify_repeat_cadence(
        raw.t,
        n_windows=fluid_report.n_windows,
        total_iterations=fluid_report.total_iterations,
        stamp=FLUID_STAMP,
    )
    forces = read_force_history(_one_force_file(fluid_dir), repeats="last")
    if forces.n_dropped and cadence.kind == "per-window":
        raise BenchmarkError(
            f"{arm}: {forces.n_dropped} force row(s) were dropped from a per-window record. "
            "That is a timePrecision collapse -- the deck sets timePrecision 12 precisely to "
            "stop it -- and the cycle means would be built from a record with holes in it."
        )

    total_force = forces.pressure + forces.viscous
    q = 0.5 * fluid.rho * fluid.u_inf**2
    area = fluid.chord * fluid.span
    # Thrust is the NEGATIVE of the streamwise force: the foil is propelling itself upstream.
    c_t = -total_force[:, 0] / (q * area)

    # --- the interface power (P2), and the cross-check that it summed the same force -----
    power_history = read_interface_power(_fluid_log(result, source), repeats="last")
    _assert_power_object_saw_the_same_force(power_history, forces, arm=arm)
    # The FO reports the rate the FLUID does work on the wall. The power INPUT to the
    # structure is that same quantity; C_P is normalised the way HG normalise it.
    c_p = power_history.power / (q * area * fluid.u_inf)

    # --- the solid's reaction power (P3), for the D10 closure identity -------------------
    reaction = read_reaction_forces(
        solid_dir / f"{solid.name}.dat",
        iterations_per_window=np.asarray(solid_report.iterations_per_window, dtype=np.int64),
    )

    # --- ONE window grid, then one time base, then one segmentation ----------------------
    # The three records do NOT share a float time axis (see `precice.schedule`): the fluid
    # FOs stamp the window START and CalculiX the window END, so index-k pairing on raw
    # times compares different physical intervals and lands in D10 and P1/P3. Each series
    # declares its convention, the window index is derived from it, and the join is on an
    # integer.
    dt = fluid.time_window_size
    indexed = {
        "force.dat": window_indices(
            forces.t, time_window_size=dt, stamp=FLUID_STAMP, label=f"{arm}: force.dat"
        ),
        "interface power": window_indices(
            power_history.t, time_window_size=dt, stamp=FLUID_STAMP, label=f"{arm}: interface power"
        ),
        "solid reaction": window_indices(
            np.asarray(reaction.times, dtype=np.float64),
            time_window_size=dt,
            stamp=SOLID_STAMP,
            label=f"{arm}: solid reaction",
        ),
    }
    try:
        windows = common_windows(indexed)
        rows = {
            label: select_windows(index, windows, label=f"{arm}: {label}")
            for label, index in indexed.items()
        }
    except ScheduleError as exc:
        raise BenchmarkError(f"{arm}: {exc}") from exc

    keep_force = rows["force.dat"]
    keep_power = rows["interface power"]
    keep_reaction = rows["solid reaction"]
    total_force = total_force[keep_force]
    c_t = c_t[keep_force]
    c_p = c_p[keep_power]
    # The ANALYSIS time base, declared once: the instant each window advanced the solution
    # TO. That is CalculiX's stamp already, and it is the physically meaningful one for a
    # quantity produced by solving the window -- the fluid's stamp is the reverted clock
    # its checkpoint left behind, not the instant its force acts at.
    window_t = windows.astype(np.float64) * dt

    # --- the naive rigid-body power (P1), for the D9 bias, from the PRESCRIBED motion -----
    # On `window_t`, so P1's velocity and P3's are evaluated at the SAME instant. Before
    # the window join these differed by one window, which is a signed bias in a REPORTED
    # quantity whose entire job is to show how biased the naive formula is.
    vy = solid.kinematics.evaluate(window_t)["vy"]
    c_p1 = -total_force[:, 1] * vy / (q * area * fluid.u_inf)
    p3 = np.asarray(reaction.forces, dtype=np.float64)[keep_reaction, 1] * vy

    history = solve.history
    if history.kind != "time":
        raise BenchmarkError(
            f"{arm}: the coupled solve reported a {history.kind!r} history; the authored "
            "path always emits a time history carrying the D0 pitch trace"
        )
    d0_deg = np.interp(window_t, np.asarray(history.t), np.asarray(history.monitor))

    analysis = analyse_limit_cycle(
        window_t,
        {C_T: c_t, C_P: c_p, C_P1: c_p1, P3: p3, D0_DEG: d0_deg},
        # D0 oscillates at the plunge frequency; thrust is at twice it, and segmenting on
        # thrust would make per-cycle amplitudes alternate between half-strokes.
        fundamental=D0_DEG,
        discard_s=spec.analysis_discard_s,
        min_cycles=spec.analysis_min_cycles,
        period=solid.kinematics.period,
    )
    mean_c_t, mean_c_p, mean_c_p1, mean_p3 = gated_means(analysis)
    mean_p2 = mean_c_p * q * area * fluid.u_inf
    if mean_c_p == 0.0 or mean_p2 == 0.0:
        raise BenchmarkError(
            f"{arm}: the cycle-mean interface power is exactly zero, so efficiency and the "
            "D10 closure ratio are both undefined. The likeliest cause is the coded "
            "function object summing a force against a stationary wall velocity."
        )

    return ArmReadout(
        arm=arm,
        run_id=solve.run_id,
        period=analysis.period,
        t_start=analysis.t_start,
        t_end=analysis.t_end,
        n_settled_cycles=analysis.n_settled_cycles,
        n_windows=int(solve.scalars["n_windows"]),
        c_t=mean_c_t,
        c_p=mean_c_p,
        # The ratio of the SAME two settled-tail integer-cycle means D1 and C_P report —
        # not a ratio over the whole post-discard record, which would mix unconverged
        # cycles into the D2-gated quantity while every sibling field excluded them
        # (session-7 adversarial review, candidate 12). Ratio of means, never mean of
        # ratios; the zero guard above already refused mean_c_p == 0.
        eta=mean_c_t / mean_c_p,
        d0_pitch_amplitude_deg=solve.scalars["d0_pitch_amplitude_deg"],
        c_p1=mean_c_p1,
        p1_p2_bias=(mean_c_p1 - mean_c_p) / mean_c_p,
        p3_p2_closure=(mean_p3 - mean_p2) / mean_p2,
        force_cadence=cadence.kind,
        force_rows_read=cadence.n_rows,
        interface_power_rows_read=int(power_history.t.size),
        n_windows_analysed=int(windows.size),
        coupling_mean_iterations=solve.scalars["coupling_mean_iterations"],
        analysis=analysis,
        force_t=tuple(float(v) for v in window_t),
    )


def _fluid_log(result: ResultHandle, source: AuthoredSource) -> Path:
    """The fluid participant's captured log, where the coded object writes its power."""
    path = result.output_host_path / "Fluid.log"
    if not path.is_file():
        raise BenchmarkError(
            f"{path}: the fluid participant's log is not in the run directory, so the "
            "interface power (P2) cannot be read. The launcher captures it; a missing log "
            f"means the run directory is incomplete (case {source.case_dir_name!r})."
        )
    return path


def _assert_power_object_saw_the_same_force(
    power_history: InterfacePowerHistory, forces: ForceHistory, *, arm: str
) -> None:
    """P2 and C_T must come from ONE force computation, not two that agree by luck.

    The coded object sums the ``force`` field the ``forces`` object itself registers, so its
    reported force total is the same number ``force.dat`` carries. Measured at twelve
    significant figures on the session-5 spike; asserted here on every run, because "they
    cannot disagree by construction" stopped being true once the two were read back by
    different code paths.
    """
    fo_force = np.asarray(power_history.force, dtype=np.float64)
    dat_force = np.asarray(forces.pressure, dtype=np.float64) + np.asarray(
        forces.viscous, dtype=np.float64
    )
    if fo_force.shape != dat_force.shape:
        raise BenchmarkError(
            f"{arm}: the interface-power object reported {fo_force.shape[0]} rows and "
            f"force.dat {dat_force.shape[0]}. They execute in the same loop at the same "
            "cadence, so a difference means one of the two files is truncated."
        )
    scale = float(np.max(np.abs(dat_force))) or 1.0
    worst = float(np.max(np.abs(fo_force - dat_force))) / scale
    if worst > 1.0e-9:
        raise BenchmarkError(
            f"{arm}: the interface-power object's summed force differs from force.dat by "
            f"{worst:.3e} relative. They are supposed to be the SAME per-face force, so P2 "
            "and C_T would be describing different loads on the same wall."
        )


def _windows_from_the_join(*, arm: str) -> None:
    """Removed: `_assert_one_schedule` compared RAW times and could only ever refuse.

    It required the three records to carry the same instants to 1e-6 of a window. They do
    not, and cannot: the fluid FOs stamp the window START and CalculiX the window END, so
    on both surviving I4 arms it failed on shape (501 instants against 500) and, had the
    shapes been forced to match, would have failed on a difference of exactly one window.

    Its job -- "every record covers the same coupling windows" -- is now done by
    `precice.schedule.common_windows`, on integer window indices derived from each
    series' DECLARED convention. That is a stronger check than the tolerance it replaced:
    it names which record is missing which windows, and it cannot be satisfied by two
    records that agree on times while describing different windows.
    """
    raise NotImplementedError(  # pragma: no cover - kept as a signpost, never called
        f"{arm}: schedule agreement is established by window index, not by raw time; see "
        "aero.adapters.precice.schedule"
    )

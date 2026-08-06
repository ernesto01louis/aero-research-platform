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
from aero.adapters.precice.solver import PreciceCoupledSolver
from aero.postprocess import LimitCycleAnalysis, analyse_limit_cycle
from aero.vv._base import BenchmarkError
from aero.vv.alignment import per_cycle_efficiency, window_efficiency

__all__ = [
    "C_P",
    "C_P1",
    "C_T",
    "D0_DEG",
    "P3",
    "ArmReadout",
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
_SCHEDULE_TOL_WINDOWS = 1.0e-6


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
    coupling_mean_iterations: float = Field(..., gt=0.0)

    # --- what the paired path needs ---
    analysis: LimitCycleAnalysis
    force_t: tuple[float, ...] = Field(..., min_length=2)

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


def _within(t: NDArray[np.float64], *, t_start: float, t_end: float) -> NDArray[np.bool_]:
    return (t >= t_start) & (t <= t_end)


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

    # --- the naive rigid-body power (P1), for the D9 bias, from the PRESCRIBED motion -----
    vy = solid.kinematics.evaluate(forces.t)["vy"]
    c_p1 = -total_force[:, 1] * vy / (q * area * fluid.u_inf)

    # --- the solid's reaction power (P3), for the D10 closure identity -------------------
    reaction = read_reaction_forces(
        solid_dir / f"{solid.name}.dat",
        iterations_per_window=np.asarray(solid_report.iterations_per_window, dtype=np.int64),
    )
    p3 = reaction.forces[:, 1] * solid.kinematics.evaluate(reaction.times)["vy"]

    # --- everything on one time base, then one segmentation ------------------------------
    _assert_one_schedule(
        {"interface power": power_history.t, "solid reaction": reaction.times},
        forces.t,
        window=fluid.time_window_size,
        arm=arm,
    )
    history = solve.history
    if history.kind != "time":
        raise BenchmarkError(
            f"{arm}: the coupled solve reported a {history.kind!r} history; the authored "
            "path always emits a time history carrying the D0 pitch trace"
        )
    d0_deg = np.interp(forces.t, np.asarray(history.t), np.asarray(history.monitor))

    analysis = analyse_limit_cycle(
        forces.t,
        {C_T: c_t, C_P: c_p, C_P1: c_p1, P3: p3, D0_DEG: d0_deg},
        # D0 oscillates at the plunge frequency; thrust is at twice it, and segmenting on
        # thrust would make per-cycle amplitudes alternate between half-strokes.
        fundamental=D0_DEG,
        discard_s=spec.analysis_discard_s,
        min_cycles=spec.analysis_min_cycles,
        period=solid.kinematics.period,
    )
    keep = _within(forces.t, t_start=analysis.t_start, t_end=analysis.t_end)
    mean_c_t = float(np.mean(c_t[keep]))
    mean_c_p = float(np.mean(c_p[keep]))
    mean_c_p1 = float(np.mean(c_p1[keep]))
    mean_p3 = float(np.mean(p3[keep]))
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
        eta=window_efficiency(
            np.asarray(analysis.cycles[C_T].per_cycle_mean, dtype=np.float64),
            np.asarray(analysis.cycles[C_P].per_cycle_mean, dtype=np.float64),
        ),
        d0_pitch_amplitude_deg=solve.scalars["d0_pitch_amplitude_deg"],
        c_p1=mean_c_p1,
        p1_p2_bias=(mean_c_p1 - mean_c_p) / mean_c_p,
        p3_p2_closure=(mean_p3 - mean_p2) / mean_p2,
        force_cadence=cadence.kind,
        force_rows_read=cadence.n_rows,
        interface_power_rows_read=int(power_history.t.size),
        coupling_mean_iterations=solve.scalars["coupling_mean_iterations"],
        analysis=analysis,
        force_t=tuple(float(v) for v in forces.t),
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


def _assert_one_schedule(
    others: dict[str, NDArray[np.float64]],
    reference: NDArray[np.float64],
    *,
    window: float,
    arm: str,
) -> None:
    """Every record covers the same coupling windows as the force history.

    NOT bitwise: these are independent ASCII accumulators written by three different
    programs, and CalculiX prints its time at seven significant digits. Bitwise equality is
    reserved for the cross-ARM comparison in ``alignment.py``, where one writer produced
    both sides and it is achievable.
    """
    tolerance = _SCHEDULE_TOL_WINDOWS * window
    for label, t in others.items():
        got = np.asarray(t, dtype=np.float64)
        if got.shape != reference.shape:
            raise BenchmarkError(
                f"{arm}: the {label} record covers {got.size} windows and the force history "
                f"{reference.size}. Every per-window record of one run has the same length; "
                "a difference means one participant stopped early or a file is truncated."
            )
        worst = float(np.max(np.abs(got - reference)))
        if worst > tolerance:
            raise BenchmarkError(
                f"{arm}: the {label} record's instants differ from the force history's by up "
                f"to {worst:.3e} s, more than {tolerance:.3e} s. The two are then indexed "
                "against different windows and every derived power is misaligned by one."
            )

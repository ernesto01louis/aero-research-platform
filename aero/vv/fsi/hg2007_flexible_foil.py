"""Heathcote & Gursul (2007) — a chordwise-flexible plunging foil, validated against experiment.

Stage 20's claim is **application fidelity**, and ADR-016 requires it never blur with Stage
19's. Turek-Hron FSI3 established that the partitioned coupling is CORRECT, on a benchmark
with a Nutils solid. This case asks a different question — does the platform reproduce what
an experiment measured? — with a CalculiX solid, two containers, and a reference that is a
water tunnel rather than a published table of another code's output.

**The flexibility is the result, not a detail.** HG measured that a moderately flexible foil
produces MORE thrust and higher propulsive efficiency than a rigid one over a range of
Strouhal numbers. That sign change is the whole reason a flapping-wing optimizer has to model
flexibility, so the gated claim is the flexible-vs-rigid INCREMENT as much as the absolute
values, and the two arms differ in exactly one number: the plate's thickness.

Two structural consequences follow, and both are why this module looks the way it does.

**Each arm is its own registered case.** ``metrics()`` returns only the clauses one arm can
measure on its own, because ``BenchmarkCase.evaluate`` sees one result. The increment clauses
D3/D4 need both arms and are composed by the campaign driver through
:func:`aero.vv.alignment.align_arms` and the paired estimator; ADR-039 records that the
increment consequently has no row on the V&V dashboard.

**The pitch is never prescribed.** The solid is driven in pure plunge from the teardrop's
leading edge; the pitch ARISES from the plate's deformation, exactly as in the experiment.
Prescribing it would model a different experiment while producing entirely plausible numbers
-- which is why ``CalculiXSolidSpec`` refuses a non-zero pitch amplitude at construction.

The reference of record is ``hg2007_recomputed.csv``: text-sourced values where the thesis
states them and 208 digitized markers where it does not, with the author-stated instrument
uncertainties (5 % thrust, 10 % efficiency) carried as ``u95_input``. Read
``data/references/fsi/heathcote_gursul_2007/reference.md`` before touching any number here --
it records two live traps, including that Figures 5.6 and 5.1 plot ``C_T/St^2`` under a
caption reading "thrust coefficient".
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aero.adapters.openfoam.flexible_foil import FlexibleFoilSpec
from aero.adapters.openfoam.geometry import hg2007_coordinates
from aero.adapters.openfoam.schemas import TeardropPlateSection
from aero.adapters.precice.calculix import CalculiXMaterial, CalculiXSolidSpec
from aero.adapters.precice.case import (
    AuthoredSource,
    CoupledCaseSpec,
    ParticipantSpec,
)
from aero.adapters.precice.template import HG2007_TEMPLATE, RENDERER_VERSION, template_sha256
from aero.postprocess.flapping_kinematics import FlappingKinematics
from aero.vv._base import BenchmarkError, MetricSpec, ReferenceData, Series, SolverLike

__all__ = [
    "ARMS",
    "CLAUSE_BANDS",
    "HG2007_CASES",
    "RUNGS",
    "Arm",
    "HeathcoteGursulFoil",
    "PredicateResult",
    "PredicateSpec",
    "evaluate_predicates",
    "hg2007_case_spec",
    "is_gated_configuration",
]

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

_REFERENCE_DIR = Path("data") / "references" / "fsi" / "heathcote_gursul_2007"
_RECOMPUTED = "hg2007_recomputed.csv"

# --------------------------------------------------------------------------------------
# The operating point -- fixed from the reference ALONE, before any solve
# --------------------------------------------------------------------------------------
# Re = 9000 is forced rather than chosen: Figure 5.13 exists only there, so it is the only
# Reynolds number at which the D0 pitch-amplitude gate has a reference at all. St = 0.345
# maximises the flexible-minus-rigid increment in C_T/St^2 inside the 0.2 < St < 0.4 band
# the thesis itself calls out as observed in nature (the originally approved "largest
# measured dC_T" rule is degenerate -- C_T scales as St^2, so dC_T rises monotonically to
# the figure's right-hand edge). ADR-039 records that selection-rule change.

CHORD_M = 0.090
PLUNGE_AMPLITUDE_M = 0.0175
#: ``h = a / c``. **0.194, not 0.175** -- 0.175 belongs to the OTHER two Heathcote
#: experiments, whose chord is 100 mm. The same shaker amplitude, a different chord.
PLUNGE_TO_CHORD = PLUNGE_AMPLITUDE_M / CHORD_M

FREESTREAM_M_S = 0.1
DENSITY_KG_M3 = 1000.0
KINEMATIC_VISCOSITY_M2_S = 1.0e-6
FREQUENCY_HZ = 0.9857142857142858  # St = 2 f a / U = 0.345
STROUHAL = 0.345
REYNOLDS = 9000.0

#: The CFD slab thickness. NOT the rig's 300 mm span: the case is quasi-2-D, and this one
#: number must feed BOTH writers -- preCICE exchanges an absolute force in newtons, so a
#: solid slab of a different thickness is loaded by the wrong amount while everything
#: converges (handoff 6.12).
SPAN_M = 0.0025

NOSE_LENGTH_M = 0.0085
MAX_HALF_THICKNESS_M = 0.0048
#: Where the teardrop has faired into the plate AND the structural root sits -- the plate is
#: clamped between the two machined leading-edge halves there.
JOIN_X_M = 0.030

#: The two arms, and the ONLY number that differs between them.
THICKNESS_RATIO = {"flexible": 0.85e-3, "rigid": 4.23e-3}
Arm = Literal["flexible", "rigid"]
ARMS: tuple[Arm, ...] = ("flexible", "rigid")

STEEL = CalculiXMaterial(name="steel", youngs_modulus=2.05e11, poisson_ratio=0.3, density=7800.0)
ALUMINIUM = CalculiXMaterial(
    name="aluminium", youngs_modulus=7.0e10, poisson_ratio=0.33, density=2700.0
)

#: The three-grid ladder, measured in session 5 and reproducing to four significant figures:
#: 45 682 / 77 240 / 130 032 cells, a uniform 2-D refinement ratio of 1.30 across both steps,
#: which is what a three-grid GCI wants. The two arms differ only in the fifth significant
#: figure of every mesh-quality metric, so the paired increment is not confounded by mesh.
RUNGS: dict[str, dict[str, int]] = {
    "coarse": {"n_surface": 83, "n_normal": 83, "n_front": 42, "n_wake": 66, "n_te": 3},
    "mid": {"n_surface": 108, "n_normal": 108, "n_front": 54, "n_wake": 86, "n_te": 4},
    "fine": {"n_surface": 140, "n_normal": 140, "n_front": 70, "n_wake": 112, "n_te": 6},
}

#: The rung and the sampling ADR-039 B2 pre-registers as GATED.
#:
#: ``None`` until the I7 max-Courant probe has measured the time step and the I4 calibrations
#: have sized the end time -- and :func:`is_gated_configuration` returns ``False`` for as long
#: as they are ``None``. That is deliberate and structural: `gated` is DERIVED, never passed
#: in, so until the pre-flight has run there is no configuration that can claim the gated
#: verdict, and the campaign cannot accidentally be launched against an ESTIMATED time step.
GATED_RUNG = "mid"
GATED_TIME_WINDOW_S: float | None = None
GATED_MAX_TIME_S: float | None = None

#: Pre-registered analysis rule. The prescribed plunge ramps over one cycle (ADR-024's
#: ``(1 - cos)`` envelope), and the discard is two further cycles beyond it.
ANALYSIS_DISCARD_S = 3.0 / FREQUENCY_HZ
ANALYSIS_MIN_CYCLES = 10


def is_gated_configuration(*, rung: str, time_window_size: float, max_time: float) -> bool:
    """Is this the ONE configuration ADR-039 B2 pre-registers as gated?

    Pure and filesystem-free, so the required CI job can guard it without a DVC pull -- the
    ``is_gated_configuration`` pattern ADR-036 B3 established.

    Returns ``False`` while ``GATED_TIME_WINDOW_S`` or ``GATED_MAX_TIME_S`` is ``None``. A
    band pre-registered against an estimated time step is not a pre-registration, and this
    is where that is structural rather than a matter of discipline.
    """
    if GATED_TIME_WINDOW_S is None or GATED_MAX_TIME_S is None:
        return False
    return (
        rung == GATED_RUNG
        and time_window_size == GATED_TIME_WINDOW_S
        and max_time == GATED_MAX_TIME_S
    )


def _repo_root() -> Path:
    # aero/vv/fsi/hg2007_flexible_foil.py -> repo root.
    return Path(__file__).resolve().parents[3]


def _reference_scalar(repo_root: Path, quantity: str) -> float:
    """One value from the reference of record."""
    path = repo_root / _REFERENCE_DIR / _RECOMPUTED
    if not path.is_file():
        raise BenchmarkError(
            f"{path} not found — run scripts/stage20_acquire_hg_reference.py to establish "
            "the Heathcote-Gursul reference of record"
        )
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    for row in csv.DictReader(lines):
        if row["quantity"] == quantity:
            return float(row["value"])
    raise BenchmarkError(f"{path}: no reference quantity {quantity!r}")


def section_for(arm: Arm) -> TeardropPlateSection:
    """The teardrop/plate section for one arm. The plate thickness IS the arm."""
    return TeardropPlateSection(
        nose_length=NOSE_LENGTH_M,
        max_half_thickness=MAX_HALF_THICKNESS_M,
        join_x=JOIN_X_M,
        plate_half_thickness=THICKNESS_RATIO[arm] * CHORD_M / 2.0,
    )


def hg2007_case_spec(
    *,
    arm: Arm,
    time_window_size: float,
    max_time: float,
    wall_clock_ceiling_s: int,
    rung: str = GATED_RUNG,
    ddt_scheme: str = "Euler",
    run_as_uid: int = 1000,
    fluid_sif: str = "precice-fsi.sif",
    solid_sif: str = "calculix-precice.sif",
) -> CoupledCaseSpec:
    """Build one arm's authored coupled case.

    ``time_window_size`` and ``max_time`` are REQUIRED and have no defaults. The campaign's
    time step is decided by the I7 max-Courant measurement and its end time by the I4
    calibrations; a default here would be an estimate that looks like a decision, and
    :func:`is_gated_configuration` would have nothing to compare against.
    """
    if rung not in RUNGS:
        raise BenchmarkError(f"unknown rung {rung!r}; have {', '.join(sorted(RUNGS))}")
    section = section_for(arm)
    knobs = RUNGS[rung]
    name = f"hg2007_{arm}_foil"

    fluid = FlexibleFoilSpec(
        name=name,
        u_inf=FREESTREAM_M_S,
        rho=DENSITY_KG_M3,
        nu=KINEMATIC_VISCOSITY_M2_S,
        chord=CHORD_M,
        span=SPAN_M,
        section=section,
        time_window_size=time_window_size,
        max_time=max_time,
        ddt_scheme=ddt_scheme,
        n_surface=knobs["n_surface"],
        n_normal=knobs["n_normal"],
        n_front=knobs["n_front"],
        n_wake=knobs["n_wake"],
        n_te=knobs["n_te"],
    )
    # The solid stands on the FLUID's stations, leading-edge point excluded, so "the solid's
    # wetted curve IS the fluid's" is an identity rather than an interpolation. Enforced
    # again by `assert_authored_consistent`; built that way here so it cannot drift.
    surface_x = tuple(
        float(v)
        for v in hg2007_coordinates(
            2 * knobs["n_surface"] + 1,
            chord=CHORD_M,
            nose_length=section.nose_length,
            max_half_thickness=section.max_half_thickness,
            join_x=section.join_x,
            plate_half_thickness=section.plate_half_thickness,
        )[1:, 0]
    )
    solid = CalculiXSolidSpec(
        name=f"hg2007-{arm}-solid",
        surface_x=surface_x,
        chord=CHORD_M,
        nose_length=section.nose_length,
        max_half_thickness=section.max_half_thickness,
        join_x=section.join_x,
        plate_half_thickness=section.plate_half_thickness,
        span=SPAN_M,
        plate=STEEL,
        nose=ALUMINIUM,
        time_window_size=time_window_size,
        max_time=max_time,
        kinematics=FlappingKinematics(
            stroke_amplitude=PLUNGE_AMPLITUDE_M,
            frequency=FREQUENCY_HZ,
            pitch_amplitude_deg=0.0,  # the pitch ARISES; prescribing it is a different case
            stroke_plane_deg=90.0,  # pure heave; at the default 0 the deck prescribes nothing
        ),
    )
    return CoupledCaseSpec(
        name=name,
        source=AuthoredSource(
            case_dir_name=f"hg2007-{arm}-foil",
            template=HG2007_TEMPLATE,
            template_sha256=template_sha256(),
            renderer_version=RENDERER_VERSION,
            fluid=fluid,
            solid=solid,
        ),
        participants=(
            ParticipantSpec(
                name="Fluid",
                workdir="fluid-openfoam",
                command="pimpleFoam",
                sif=fluid_sif,
                run_as_uid=run_as_uid,
            ),
            ParticipantSpec(
                name="Solid",
                workdir="solid-calculix",
                command=f"ccx_preCICE -i {solid.name} -precice-participant Solid",
                sif=solid_sif,
                run_as_uid=run_as_uid,
            ),
        ),
        container_of_record=fluid_sif,
        max_time=max_time,
        wall_clock_ceiling_s=wall_clock_ceiling_s,
        analysis_discard_s=ANALYSIS_DISCARD_S,
        analysis_min_cycles=ANALYSIS_MIN_CYCLES,
        run_as_uid=run_as_uid,
        # DERIVED, never passed in -- so a diagnostic rung cannot claim the gated verdict.
        gated=is_gated_configuration(
            rung=rung, time_window_size=time_window_size, max_time=max_time
        ),
    )


# --------------------------------------------------------------------------------------
# The clause registry — ONE ordered place a clause is bound to a band
# --------------------------------------------------------------------------------------
# ADR-036's parity test omitted its band-less clauses, and that is exactly how D9 and D10
# vanished from it silently. Here `(no band)` is a first-class VALUE, so a clause without a
# numeric band still has a row and the ordered parity test still sees it.

BandToken = str

#: Every D-family clause, in order, with the band token it carries in ADR-039's gate block.
CLAUSE_BANDS: tuple[tuple[str, BandToken], ...] = (
    ("D0", "25 %"),
    ("D1", "25 %"),
    ("D2", "40 %"),
    ("D3", "25 %"),
    ("D4", "25 %"),
    ("D5", "(no band)"),
    ("D6", "(no band)"),
    ("D7", "(no band)"),
    ("D8", "2 deg"),
    ("D9", "(no band)"),
    ("D10", "2 %"),
)

#: Clause -> the measured scalar's name, for the banded clauses one ARM can measure.
#: D3/D4 are absent because they need both arms; the driver composes them.
CLAUSE_METRIC: dict[Arm, tuple[tuple[str, str], ...]] = {
    "flexible": (
        ("D0", "d0_pitch_amplitude_deg"),
        ("D1", "c_t"),
        ("D2", "eta"),
        ("D10", "p3_p2_closure"),
    ),
    "rigid": (
        ("D8", "d0_pitch_amplitude_deg"),
        ("D10", "p3_p2_closure"),
    ),
}

#: Bands, computed in session 3 by the pre-registered rule ``4 x (u95_ref / |value|)``,
#: floored at 0.25 and capped at 0.50. **The cap never binds and the floor binds four times
#: out of five**, so for D3 and D4 the 4x rule is decorative and 0.25 is a policy number --
#: ADR-039 says so in those words rather than letting the formula imply otherwise.
BANDS: dict[str, float] = {
    "D0": 0.25,
    "D1": 0.25,
    "D2": 0.40,
    "D3": 0.25,
    "D4": 0.25,
    "D8": 2.0,  # degrees, ABSOLUTE against a declared reference of 0
    "D10": 0.02,  # ABSOLUTE against a declared reference of 0
}

#: Clauses that are REPORTED and never gated. D9 is here by operator decision: D8 admits up
#: to 2 degrees of rigid-arm pitch, worth 12 % of the trailing edge's velocity, while P1
#: assumes a single rigid-body velocity -- so D8 and D9 could not both be satisfiable in the
#: worst admissible case and a D9 NO-GO would have said nothing about the physics.
REPORTED_ONLY: tuple[str, ...] = ("D9",)


class PredicateSpec(BaseModel):
    """A structural clause: something that must be TRUE, with no numeric band."""

    model_config = _STRICT

    clause: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    inadmissible: bool = Field(
        default=False,
        description=(
            "When True, failure RAISES rather than producing a NO-GO: the result is a broken "
            "record, not evidence about the physics."
        ),
    )


class PredicateResult(BaseModel):
    model_config = _STRICT

    clause: str
    name: str
    passed: bool
    detail: str


PREDICATES: tuple[PredicateSpec, ...] = (
    PredicateSpec(
        clause="D5",
        name="thrust_increment_is_positive",
        description=(
            "The flexible foil produces MORE thrust than the rigid one. This is HG's headline "
            "result; a negative increment is a real physical NO-GO, so it does not raise."
        ),
    ),
    PredicateSpec(
        clause="D6",
        name="efficiency_increment_is_positive",
        description="The flexible foil is MORE efficient than the rigid one (HG Fig 5.9a).",
    ),
    PredicateSpec(
        clause="D7",
        name="both_arms_are_admissible",
        description=(
            "Each arm reports C_T > 0 and 0 < eta < 1. A foil that produces net drag, or an "
            "efficiency outside the unit interval, is a broken record rather than a "
            "disagreement with the experiment -- so this RAISES."
        ),
        inadmissible=True,
    ),
)


def evaluate_predicates(flexible: Any, rigid: Any) -> tuple[PredicateResult, ...]:
    """Evaluate D5/D6/D7 over two :class:`~aero.vv.fsi.hg2007_readout.ArmReadout` arms.

    D7 raises; D5 and D6 report. The distinction is the point: an inadmissible number means
    the measurement is broken, while a negative increment means the platform did not
    reproduce the experiment -- which is a result, and the verdict resolves clause by clause
    so it can be stated as one.
    """
    inadmissible = [
        f"{arm.arm}: C_T = {arm.c_t:.4g}, eta = {arm.eta:.4g}"
        for arm in (flexible, rigid)
        if not (arm.c_t > 0.0 and 0.0 < arm.eta < 1.0)
    ]
    if inadmissible:
        raise BenchmarkError(
            "D7: an arm reported an inadmissible result — "
            + "; ".join(inadmissible)
            + ". C_T <= 0 is net drag and eta outside (0, 1) is not an efficiency; either "
            "makes the record broken rather than a disagreement with the experiment. Do not "
            "report this as a NO-GO — investigate the readout."
        )
    d_c_t = flexible.c_t - rigid.c_t
    d_eta = flexible.eta - rigid.eta
    return (
        PredicateResult(
            clause="D5",
            name="thrust_increment_is_positive",
            passed=d_c_t > 0.0,
            detail=f"dC_T = {d_c_t:+.6g} ({flexible.c_t:.6g} - {rigid.c_t:.6g})",
        ),
        PredicateResult(
            clause="D6",
            name="efficiency_increment_is_positive",
            passed=d_eta > 0.0,
            detail=f"d_eta = {d_eta:+.6g} ({flexible.eta:.6g} - {rigid.eta:.6g})",
        ),
        PredicateResult(
            clause="D7",
            name="both_arms_are_admissible",
            passed=True,
            detail="both arms report C_T > 0 and 0 < eta < 1",
        ),
    )


# --------------------------------------------------------------------------------------
# The BenchmarkCase — one per arm
# --------------------------------------------------------------------------------------

#: Reference rows in ``hg2007_recomputed.csv``, per arm and metric.
_REFERENCE_ROW: dict[Arm, dict[str, str]] = {
    "flexible": {
        "d0_pitch_amplitude_deg": "pitch_amplitude_flexible",
        "c_t": "thrust_coefficient_flexible",
        "eta": "propulsive_efficiency_flexible",
    },
    "rigid": {
        "c_t": "thrust_coefficient_rigid",
        "eta": "propulsive_efficiency_rigid",
    },
}


class HeathcoteGursulFoil:
    """One arm of the Heathcote-Gursul flexible-foil validation."""

    sweep_metric = "c_t"

    def __init__(self, arm: Arm = "flexible", spec: CoupledCaseSpec | None = None) -> None:
        self.arm = arm
        self.name = f"hg2007_{arm}_foil"
        self.description = (
            f"Heathcote & Gursul (2007) chordwise-flexible plunging foil, {arm} arm "
            f"(b/c = {THICKNESS_RATIO[arm]:.2e}) at Re = {REYNOLDS:.0f}, St = {STROUHAL} — "
            "OpenFOAM fluid + CalculiX solid through preCICE, against the water-tunnel "
            "measurement."
        )
        self._spec = spec

    def case_spec(self) -> CoupledCaseSpec:
        if self._spec is None:
            if GATED_TIME_WINDOW_S is None or GATED_MAX_TIME_S is None:
                raise BenchmarkError(
                    f"{self.name}: the campaign's time-window size and end time are decided "
                    "by the I7 max-Courant probe and the I4 calibrations, and neither has "
                    "been pre-registered in ADR-039 B2 yet. Build the spec explicitly with "
                    "hg2007_case_spec(time_window_size=..., max_time=...) — there is "
                    "deliberately no default, because a default here would be an estimate "
                    "wearing a decision's clothes."
                )
            self._spec = hg2007_case_spec(
                arm=self.arm,
                time_window_size=GATED_TIME_WINDOW_S,
                max_time=GATED_MAX_TIME_S,
                wall_clock_ceiling_s=14 * 24 * 3600,
            )
        return self._spec

    def reference(self, repo_root: Path) -> ReferenceData:
        scalars = {
            metric: _reference_scalar(repo_root, row)
            for metric, row in _REFERENCE_ROW[self.arm].items()
        }
        # D8 and D10 are compared ABSOLUTELY against zero. Those zeros are DECLARED by
        # construction, not measured: hg2007_recomputed.csv has no row for either, because
        # neither is something the experiment reports.
        if self.arm == "rigid":
            scalars["d0_pitch_amplitude_deg"] = 0.0
        scalars["p3_p2_closure"] = 0.0
        return ReferenceData(
            case_name=self.name,
            source=(
                "Heathcote & Gursul (2007) / Heathcote thesis Ch. 5, recomputed into "
                "hg2007_recomputed.csv from text-sourced values and 208 digitized markers. "
                "The D8 and D10 references of 0.0 are DECLARED by construction (a rigid "
                "arm's pitch, and an exact power-closure identity), not measured — the "
                "reference file carries no row for either."
            ),
            scalars=scalars,
        )

    def metrics(self) -> tuple[MetricSpec, ...]:
        """The clauses THIS arm can measure on its own.

        D3/D4 -- the increment, and the mission-shaped claim -- need both arms and are
        composed by the campaign driver, not here. ADR-039 records that the increment
        therefore has no V&V dashboard row.
        """
        specs: list[MetricSpec] = []
        for clause, metric in CLAUSE_METRIC[self.arm]:
            specs.append(
                MetricSpec(
                    name=metric,
                    kind="scalar",
                    tolerance=BANDS[clause],
                    # D8 (a pitch angle) and D10 (a closure ratio) are compared against a
                    # declared zero, where a relative comparison is undefined.
                    comparison="absolute" if clause in {"D8", "D10"} else "relative",
                )
            )
        return tuple(specs)

    def predicates(self) -> tuple[PredicateSpec, ...]:
        """The band-less structural clauses, in a registry parallel to :meth:`metrics`.

        Separate because ``MetricSpec`` can only express a numeric band, and a sign or an
        admissibility check is not one. Carrying them as fake bands would put a number in
        the gate block that means nothing.
        """
        return PREDICATES

    def evaluate(self, solver: SolverLike, result: Any) -> dict[str, float | Series]:
        """Measure this arm.

        Goes through :func:`aero.vv.fsi.hg2007_readout.read_arm`, which calls
        ``solver.load()`` first -- so K2, C4, K1 and the periodic-steady-state check have all
        run before any number here exists, and the analysis window comes from the gated solve
        rather than from this method.
        """
        from aero.adapters.precice.solver import PreciceCoupledSolver
        from aero.vv.fsi.hg2007_readout import read_arm

        if not isinstance(solver, PreciceCoupledSolver):
            raise BenchmarkError(
                f"{self.name} is driven by PreciceCoupledSolver only (the readout reads a "
                f"coupled case's own file layout), got {type(solver).__name__}"
            )
        readout = read_arm(solver, result, arm=self.arm)
        measured: dict[str, float | Series] = {}
        for _, metric in CLAUSE_METRIC[self.arm]:
            measured[metric] = getattr(readout, metric)
        return measured

    def refined(self, ratio: float) -> HeathcoteGursulFoil:
        """Not available in-process: the GCI runs as a campaign, not as a mesh sweep.

        The ladder is real and pre-registered -- three self-similar rungs at a uniform 1.30
        refinement ratio -- but each rung is a multi-day coupled solve with its own
        wall-clock ceiling, launched in waves. Running three of them inside ``aero vv run``
        would silently exceed every budget the pre-registration declares.
        """
        raise NotImplementedError(
            "hg2007 runs its grid-convergence study as a pre-registered CAMPAIGN across the "
            f"rungs {sorted(RUNGS)} (ADR-039 B2), not as an in-process MeshSweep: each rung "
            "is a multi-day coupled solve with its own ceiling. Build the rungs explicitly "
            "with hg2007_case_spec(rung=...)."
        )


HG2007_CASES: dict[str, HeathcoteGursulFoil] = {
    case.name: case for case in (HeathcoteGursulFoil(arm) for arm in ARMS)
}

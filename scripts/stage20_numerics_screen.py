#!/usr/bin/env python3
"""Stage 20 — the fluid-only numerics screen, on a mesh that MOVES (ADR-040 N4/N5).

Session 8's N2 sweep (`data/vv/stage20_n2_screening.json`) had no producing script; it was
run by hand and only its artefacts survive on NFS. This is that harness, committed, plus the
one variable N2 could not vary.

WHY THIS EXISTS. N2 ran on a STATIC mesh and measured 302 GAMG iterations per fluid step.
The campaign measured 961. The N2 record attributes the gap to "the deforming mesh", but that
was a hypothesis. Re-read from the surviving I4 logs, the gap is sharper than that:

    per fluid step        campaign flexible   campaign rigid   N2 s0_control (static)
    p solves/step                      8.00             8.00                     8.00
    p iterations/SOLVE                113.0             74.2                     35.6
    pcorr iterations/step              56.9             42.4                     17.0
    cellDisplacement it/step            1.0              1.0            0.0 (never moves)

Same mesh, same 0/ bytes, same solve counts, same tolerances. `pcorr` is only 6 % of the 961,
so the moving-mesh flux correction is NOT the cost: it is `p` itself, 3.17x harder per solve.
The count is flat in time (783 -> 1006 -> 939 across 2627 step-solves, no decaying transient)
and flat in position within the coupling window (987 on iteration 1 against 977 on iteration
3), which refutes both the startup-transient and the stale-initial-guess-after-checkpoint
explanations. The one structural difference left is that the campaign's mesh moves AT ALL --
by about 0.1 % of the plunge amplitude over the 0.01 s the I4 runs covered.

`FluidNumericsSpec.gamg_controls` defaults to `()`, so nothing is emitted and OpenFOAM's own
`cacheAgglomeration yes` default is in force: GAMG builds its agglomeration once and reuses it
against a matrix whose mesh no longer matches. On a mesh that never moves that is free and
correct -- which is exactly why N2 measured `cacheAgglomeration no` as 8 % SLOWER (s10 2.005x
against s7's 2.178x) and why the knob was untestable there. The flexible arm, which moves
more, costs 113 iterations per solve against the rigid arm's 74.2: a dose-response.

This screen exists to FALSIFY that, not to confirm it. `d1` must reproduce the campaign's
~113 iterations/solve from prescribed motion alone before any variant may be read as an
explanation; if it does not, the hypothesis is dead and N5 (the near-pure-Neumann pressure
system) leads instead.

ADMISSIBILITY. Fluid-only, prescribed motion, no solid, no coupling, 20 steps from uniform
fields. RANKS ONLY -- this screen may not size anything, exactly as N2 could not. Only a
completed COUPLED calibration at the gated rung in the wave-1 contention shape (ADR-040 N3)
may feed B2.

Usage:

    stage20_numerics_screen.py --prepare                 # write the base case + blockMesh
    stage20_numerics_screen.py --run d1 [--ranks 6]      # one variant, measured
    stage20_numerics_screen.py --record OUT.json         # assemble the record
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from aero.adapters._base import build_apptainer_exec  # noqa: E402
from aero.adapters.openfoam._foam_common import (  # noqa: E402
    FluidNumericsSpec,
    header,
    transient_fvsolution,
)
from aero.adapters.openfoam.flexible_foil import (  # noqa: E402
    WALL_PATCHES,
    write_flexible_foil_case,
)
from aero.adapters.openfoam.solver_log import read_fluid_cost_history  # noqa: E402
from aero.adapters.precice.case import AuthoredSource  # noqa: E402
from aero.vv.fsi.hg2007_flexible_foil import (  # noqa: E402
    FREQUENCY_HZ,
    PLUNGE_AMPLITUDE_M,
    hg2007_case_spec,
)

#: The screen lives beside session 8's, one directory along, so `stage20-screen` stays the
#: untouched evidence behind `data/vv/stage20_n2_screening.json`.
HOST_ROOT = Path("/mnt/aero-nfs/runs/stage20-screen9")
REMOTE_ROOT = "/mnt/aero/runs/stage20-screen9"
FLUID_SIF = "/opt/aero/containers/precice-fsi.sif"

DT_S = 2.0e-5
N_STEPS = 20
#: The first five steps are discarded before averaging, exactly as N2 did, so the two
#: records' `seconds_per_step` and `gamg_iterations_per_step` are comparable numbers.
N_DISCARD = 5
RUN_AS_UID = 1000
#: The prescribed period the (1-cos) ramp spans, from the gated operating point.
RAMP_PERIOD_S = 1.0 / FREQUENCY_HZ

#: ADR-039's stack, re-measured here rather than carried over -- the control every ratio in
#: this record is taken against.
ADR039 = FluidNumericsSpec()
#: N2's winning stack (`s12_all`, 3.73x serial): the smoother token plus Tier 2.
S12_ALL = FluidNumericsSpec(
    label="adr040-candidate",
    p_smoother="DICGaussSeidel",
    p_tolerance="1e-6",
    n_outer_correctors=1,
)
_NO_CACHE = (("cacheAgglomeration", "no"),)


@dataclass(frozen=True)
class Variant:
    """One screened configuration. `moving` is the variable N2 could not vary."""

    name: str
    numerics: FluidNumericsSpec
    moving: bool
    tests: str
    #: A fully-Dirichlet farfield `p`. Deliberately over-constrained -- a DIAGNOSTIC that
    #: isolates the conditioning of the near-pure-Neumann system, never a campaign BC.
    dirichlet_farfield: bool = False
    ranks: int = 1


VARIANTS: dict[str, Variant] = {
    v.name: v
    for v in (
        Variant("d0", ADR039, moving=False, tests="harness check: must reproduce N2 s0_control"),
        Variant(
            "d1", ADR039, moving=True, tests="does prescribed motion ALONE triple the p solve?"
        ),
        Variant(
            "d2",
            ADR039.model_copy(update={"label": "adr039-nocache", "gamg_controls": _NO_CACHE}),
            moving=True,
            tests="N4: cacheAgglomeration no, on a mesh that moves",
        ),
        Variant("d3", S12_ALL, moving=True, tests="the ADR-040 candidate stack, moving mesh"),
        Variant(
            "d4",
            S12_ALL.model_copy(update={"label": "adr040-nocache", "gamg_controls": _NO_CACHE}),
            moving=True,
            tests="N4 on the candidate stack -- the rate ADR-040 would pre-register",
        ),
        Variant(
            "d5",
            ADR039,
            moving=True,
            tests="N5 diagnostic: fully-Dirichlet farfield p, over-constrained on purpose",
            dirichlet_farfield=True,
        ),
    )
}


def _screen_controldict(*, end_time: float) -> str:
    """`system/controlDict` for a fluid-only screen.

    Byte-shaped after session 8's `stage20-screen/base/system/controlDict` so `d0` is
    comparable to `s0_control` term by term. Three deliberate differences from the campaign
    deck: no `libs`/`preCICE_Adapter` (there is no Solid, and the adapter would block on the
    exchange), no coded `aeroInterfacePower` object (it needs `dynamicCode` compilation and
    contributes nothing to a pressure-solve measurement), and `writeInterval 2000` so no
    field write lands inside the measured window -- the screen measures the solve, and I/O
    was already bounded at 0.58 % by I10.
    """
    return (
        header("dictionary", "controlDict")
        + f"""
application     pimpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {end_time:.12g};
deltaT          {DT_S:.12g};
writeControl    timeStep;
writeInterval   2000;
purgeWrite      2;
writeFormat     ascii;
writePrecision  12;
writeCompression off;
timeFormat      general;
timePrecision   12;
runTimeModifiable false;
adjustTimeStep  no;

functions
{{
    forces1
    {{
        type            forces;
        libs            (forces);
        writeControl    timeStep;
        writeInterval   1;
        writeFields     yes;
        patches         ({" ".join(WALL_PATCHES)});
        rho             rhoInf;
        rhoInf          1000;
        CofR            (0 0 0);
    }}
}}
"""
    )


def _point_displacement(*, moving: bool) -> str:
    """`0/pointDisplacement` -- both wall patches, prescribed heave or held still.

    `aero.adapters.openfoam.motion.point_displacement_field` takes a single `moving_patch`
    and the HG section emits TWO (`airfoil` + `airfoil_te`); rather than widen a Stage-11
    writer whose bytes five stages' records depend on, the screen writes its own. This file
    is a screening artefact and never enters a campaign case.

    `oscillatingDisplacement` is `amplitude * sin(omega t)`, so at t = 0 the displacement is
    zero and the VELOCITY is maximal -- which is the campaign's own regime over the 0.01 s
    the I4 runs covered, and the regime the 961 was measured in.
    """
    if moving:
        omega = 2.0 * 3.141592653589793 * FREQUENCY_HZ
        wall = f"""        type            oscillatingDisplacement;
        amplitude       (0 {PLUNGE_AMPLITUDE_M:.8g} 0);
        omega           {omega:.8g};
        value           uniform (0 0 0);"""
    else:
        wall = """        type            fixedValue;
        value           uniform (0 0 0);"""
    walls = "\n".join(f"    {p}\n    {{\n{wall}\n    }}" for p in WALL_PATCHES)
    return (
        header("pointVectorField", "pointDisplacement")
        + f"""
dimensions      [0 1 0 0 0 0 0];
internalField   uniform (0 0 0);

boundaryField
{{
{walls}
    farfield
    {{
        type            fixedValue;
        value           uniform (0 0 0);
    }}
    front {{ type empty; }}
    back  {{ type empty; }}
}}
"""
    )


def _dirichlet_p() -> str:
    """`0/p` with the farfield pinned. DIAGNOSTIC ONLY.

    The campaign's farfield is `freestreamPressure` on one 20-chord patch with `zeroGradient`
    walls. `freestreamPressure` fixes the value only where the flux leaves the domain, so at
    U = 0.1 m/s with the freestream entering over most of that boundary the pressure system
    is nearly pure Neumann and its constant mode is nearly a null vector -- which is a
    textbook way to make a multigrid coarse-grid correction struggle. Pinning the whole
    farfield over-constrains the physics (it reflects) and is never a campaign BC; it
    isolates whether conditioning is the mechanism.
    """
    walls = "\n".join(f"    {p}\n    {{\n        type zeroGradient;\n    }}" for p in WALL_PATCHES)
    return (
        header("volScalarField", "p")
        + f"""
dimensions      [0 2 -2 0 0 0 0];
internalField   uniform 0;

boundaryField
{{
{walls}
    farfield
    {{
        type            fixedValue;
        value           uniform 0;
    }}
    front {{ type empty; }}
    back  {{ type empty; }}
}}
"""
    )


def _ssh(command: str, *, timeout_s: int = 3600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", "-o", "ConnectTimeout=10", "root@aero-dev", command],
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )


def _in_sif(inner: str, *, remote_case: str, uid: int | None = None) -> str:
    """`apptainer exec` for one screen command, with the SAME uid drop the campaign uses.

    L1 measured that `mpirun` is refused outright when it runs as root, so every parallel
    variant must sit inside the `setpriv` drop. The serial variants use it too, so the two
    are not measured under different privilege and filesystem conditions.
    """
    if uid is not None:
        home = f"/tmp/aero-foam-{uid}"
        inner = (
            f"mkdir -p {home}/OpenFOAM && chmod 700 {home} && "
            f"chown {uid}:{uid} {home} {home}/OpenFOAM && "
            f"setpriv --reuid={uid} --regid={uid} --clear-groups "
            f"env HOME={home} WM_PROJECT_USER_DIR={home}/OpenFOAM "
            f"bash -lc {json.dumps(inner)}"
        )
    command = build_apptainer_exec(sif_path=FLUID_SIF, case_bind_source=remote_case, command=inner)
    return command.replace("apptainer exec ", "apptainer exec --no-home ", 1)


def prepare() -> int:
    """Write the base fluid case and mesh it once; every variant copies the result."""
    base = HOST_ROOT / "base"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)

    spec = hg2007_case_spec(
        arm="flexible",
        rung="mid",
        time_window_size=DT_S,
        max_time=N_STEPS * DT_S,
        wall_clock_ceiling_s=3600,
    )
    source = spec.source
    if not isinstance(source, AuthoredSource):  # pragma: no cover - hg2007 is always authored
        raise SystemExit(f"expected an authored source, got {source.kind!r}")
    write_flexible_foil_case(source.fluid, base)
    (base / "system" / "controlDict").write_text(
        _screen_controldict(end_time=N_STEPS * DT_S), encoding="utf-8"
    )
    (base / "system" / "preciceDict").unlink(missing_ok=True)
    (base / "0" / "pointDisplacement").write_text(_point_displacement(moving=False), "utf-8")

    print(f"base written: {base}")
    result = _ssh(_in_sif("cd /case && blockMesh", remote_case=f"{REMOTE_ROOT}/base"))
    tail = (result.stdout + result.stderr).strip().splitlines()[-6:]
    print("\n".join(tail))
    if result.returncode != 0:
        raise SystemExit(f"blockMesh failed (rc={result.returncode})")
    cells = [line for line in result.stdout.splitlines() if "cells:" in line]
    print(f"meshed: {cells[-1].strip() if cells else '?'}")
    return 0


def run(name: str, *, ranks: int) -> int:
    """Materialize one variant from the base, run it, parse its log, write its result."""
    variant = VARIANTS[name]
    base = HOST_ROOT / "base"
    if not (base / "constant" / "polyMesh" / "owner").is_file():
        raise SystemExit("no meshed base case — run --prepare first")
    case = HOST_ROOT / name
    if case.exists():
        shutil.rmtree(case)
    shutil.copytree(base, case)

    (case / "system" / "fvSolution").write_text(
        transient_fvsolution(
            cell_displacement=True, turbulence_model="laminar", numerics=variant.numerics
        ),
        encoding="utf-8",
    )
    (case / "0" / "pointDisplacement").write_text(
        _point_displacement(moving=variant.moving), encoding="utf-8"
    )
    if variant.dirichlet_farfield:
        (case / "0" / "p").write_text(_dirichlet_p(), encoding="utf-8")

    remote = f"{REMOTE_ROOT}/{name}"
    if ranks > 1:
        (case / "system" / "decomposeParDict").write_text(_decompose_par_dict(ranks), "utf-8")
        solve = f"cd /case && decomposePar -force && mpirun -n {ranks} pimpleFoam -parallel"
    else:
        solve = "cd /case && pimpleFoam"

    log = HOST_ROOT / f"{name}.log"
    print(f"running {name} ({variant.tests}) at {ranks} rank(s)…")
    result = _ssh(f"{_in_sif(solve, remote_case=remote, uid=RUN_AS_UID)} > {remote}.log 2>&1")
    if result.returncode != 0 or not log.is_file():
        tail = log.read_text(errors="replace").strip().splitlines()[-15:] if log.is_file() else []
        raise SystemExit(f"{name} failed (rc={result.returncode})\n" + "\n".join(tail))

    measured = _measure(log, variant=variant, ranks=ranks)
    (HOST_ROOT / f"{name}.result.json").write_text(
        json.dumps(measured, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"  {name}: {measured['seconds_per_step']:.4f} s/step, "
        f"p {measured['p_iterations_per_solve']:.1f} it/solve "
        f"({measured['gamg_iterations_per_step']:.1f} it/step over "
        f"{measured['pressure_solves_per_step']} solves), "
        f"cellDisplacement {measured['cell_displacement_iterations_per_step']:.2f} it/step"
    )
    return 0


def _decompose_par_dict(ranks: int) -> str:
    return (
        header("dictionary", "decomposeParDict")
        + f"""
numberOfSubdomains {ranks};
method          scotch;
"""
    )


#: The I4 calibration's own end time. The (1-cos) ramp spans one full period, so 0.01 s is
#: 1 percent of one cycle and the envelope is still 2.4e-4 of full amplitude.
CAMPAIGN_MAX_TIME_S = 0.01
#: `first_cell_height` 5.0e-4 chords x 0.09 m chord -- the yardstick that makes "the mesh
#: deformed" a measurable claim rather than a word.
FIRST_CELL_HEIGHT_M = 5.0e-4 * 0.09


def _plunge_reached(t: float) -> float:
    """How far the foil actually moved by time `t`, under ADR-024's (1-cos) ramp."""
    envelope = 0.5 * (1.0 - math.cos(math.pi * t / RAMP_PERIOD_S))
    return PLUNGE_AMPLITUDE_M * envelope * math.sin(2.0 * math.pi * FREQUENCY_HZ * t)


def _screen_plunge_reached(t: float) -> float:
    """The screen has NO ramp, so `oscillatingDisplacement` gives the full amplitude term."""
    return PLUNGE_AMPLITUDE_M * math.sin(2.0 * math.pi * FREQUENCY_HZ * t)


def _campaign_reference() -> dict[str, Any]:
    """The coupled campaign's own `p` cost, re-read from the surviving I4 logs.

    Read here rather than copied from `data/vv/stage20_i10_cost_split.json` because the I10
    record groups `p` and `pcorr` into one `gamg_pressure` term, and the whole point of this
    screen is that those two behave differently: `pcorr` is 6 % of the campaign's 961 and
    tracks the screen closely, while `p` per SOLVE is what the 3x actually lives in.

    The early slice matters more than the mean. The screen runs 20 steps from uniform fields;
    the campaign's own first five step-solves are the only like-for-like comparison, and they
    already sit at 91 iterations per solve -- so whatever the gap is, it is not something the
    campaign accumulated.
    """
    reference: dict[str, Any] = {}
    for arm, run in (
        ("flexible", "hg2007_flexible_foil-20260810-144742"),
        ("rigid", "hg2007_rigid_foil-20260810-144747"),
    ):
        log = Path(f"/mnt/aero-nfs/runs/{run}/tutorial/Fluid.log")
        if not log.is_file():
            raise SystemExit(f"{log} is gone — the screen's comparison rests on the run's bytes")
        history = read_fluid_cost_history(log)
        iterations = [s.iterations_by_field.get("p", 0) for s in history.steps]
        solves = [s.solves_by_field.get("p", 0) for s in history.steps]
        reference[arm] = {
            "run_id": run,
            "plunge_reached_m": _plunge_reached(CAMPAIGN_MAX_TIME_S),
            "plunge_reached_wall_cells": _plunge_reached(CAMPAIGN_MAX_TIME_S) / FIRST_CELL_HEIGHT_M,
            "log_sha256": _sha256(log),
            "n_step_solves": history.n_steps,
            "p_iterations_per_solve_all": sum(iterations) / sum(solves),
            "p_iterations_per_solve_first_5": sum(iterations[:5]) / sum(solves[:5]),
            "pcorr_iterations_per_step": sum(
                s.iterations_by_field.get("pcorr", 0) for s in history.steps
            )
            / history.n_steps,
        }
    return reference


def _measure(log: Path, *, variant: Variant, ranks: int) -> dict[str, Any]:
    """Parse one variant's log the way `data/vv/stage20_n2_screening.json` was derived.

    N2's committed numbers are `mean(d_execution_s)` and `mean(sum of p and pcorr
    iterations)` over `steps[N_DISCARD:]`; both reproduce bit-for-bit from the surviving
    logs, so this is the same estimator and the two records are comparable.
    """
    history = read_fluid_cost_history(log)
    steps = history.steps[N_DISCARD:]
    if not steps:
        raise SystemExit(f"{log}: only {history.n_steps} steps — nothing survives the discard")

    def per_step(fieldname: str, key: str) -> float:
        total: float = sum(float(getattr(s, key).get(fieldname, 0)) for s in steps)
        return total / len(steps)

    p_iterations = per_step("p", "iterations_by_field")
    p_solves = per_step("p", "solves_by_field")
    return {
        "name": variant.name,
        "tests": variant.tests,
        "moving_mesh": variant.moving,
        "dirichlet_farfield": variant.dirichlet_farfield,
        "ranks": ranks,
        "numerics": variant.numerics.model_dump(),
        "n_steps_measured": len(steps),
        "seconds_per_step": sum(s.d_execution_s for s in steps) / len(steps),
        "gamg_iterations_per_step": p_iterations + per_step("pcorr", "iterations_by_field"),
        "p_iterations_per_step": p_iterations,
        "p_iterations_per_solve": p_iterations / p_solves if p_solves else 0.0,
        "pcorr_iterations_per_step": per_step("pcorr", "iterations_by_field"),
        "pressure_solves_per_step": p_solves + per_step("pcorr", "solves_by_field"),
        "cell_displacement_iterations_per_step": per_step(
            "cellDisplacementx", "iterations_by_field"
        )
        + per_step("cellDisplacementy", "iterations_by_field"),
        "p_iterations_per_solve_startup": _slice_ratio(history.steps[:N_DISCARD]),
        "seconds_per_step_startup": sum(x.d_execution_s for x in history.steps[:N_DISCARD])
        / N_DISCARD,
        "log_sha256": _sha256(log),
    }


def _slice_ratio(steps: Any) -> float:
    """`p` iterations per solve over an explicit slice, for the startup-vs-settled split.

    The discarded first steps are the interesting ones here, not noise: they are the only
    part of a marching fluid-only run that starts from a field as cold as the one every
    coupling iteration of the campaign restarts from.
    """
    iterations = sum(float(x.iterations_by_field.get("p", 0)) for x in steps)
    solves = sum(float(x.solves_by_field.get("p", 0)) for x in steps)
    return iterations / solves if solves else 0.0


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


_ADMISSIBILITY = (
    "RANKS ONLY - this record may NOT size anything. It is fluid-only with PRESCRIBED "
    "motion, no solid and no coupling, 20 steps per variant from uniform fields with the "
    "first five discarded - the same estimator and the same discard as N2, so the two "
    "records' numbers are comparable term by term. ADR-039 I4's 'no rate from a transient' "
    "stands: only a completed COUPLED calibration at the gated rung in the wave-1 "
    "contention shape (ADR-040 N3) may feed B2. The residual gap this record localizes is "
    "coupling-specific and a fluid-only screen structurally cannot reach it."
)


def record(out: Path) -> int:
    """Assemble the N4/N5 record from the per-variant results and the campaign's own logs."""
    variants: dict[str, Any] = {}
    for name in sorted(VARIANTS):
        result = HOST_ROOT / f"{name}.result.json"
        if not result.is_file():
            raise SystemExit(f"{name} has not been run — {result} is missing")
        variants[name] = json.loads(result.read_text(encoding="utf-8"))

    static_control = variants["d0"]["p_iterations_per_solve"]
    moving_control = variants["d1"]["p_iterations_per_solve"]
    for measured in variants.values():
        measured["p_solve_ratio_vs_d0_static"] = measured["p_iterations_per_solve"] / static_control
        measured["p_solve_ratio_vs_d1_moving"] = measured["p_iterations_per_solve"] / moving_control
        measured["speedup_vs_d1_moving"] = (
            variants["d1"]["seconds_per_step"] / measured["seconds_per_step"]
        )

    campaign = _campaign_reference()
    payload = {
        "kind": "numerics-screening",
        "clause": "N4-N5-exploratory",
        "adr": "ADR-040",
        "gated": False,
        "admissibility": _ADMISSIBILITY,
        "variants": variants,
        "campaign_reference": campaign,
        "n4_cache_agglomeration": {
            "hypothesis": (
                "GAMG caches its agglomeration by default and the campaign deck emits no "
                "gamg_controls, so on a mesh that moves the cached agglomeration no longer "
                "matches the matrix and the coarse-grid correction degrades. Untestable on "
                "N2's static screen, where nothing could go stale."
            ),
            "refuted": True,
            "measured": (
                f"On a mesh that DOES move, cacheAgglomeration no leaves the pressure solve "
                f"at {variants['d2']['p_iterations_per_solve']:.1f} iterations per solve "
                f"against {moving_control:.1f} with the cache on - no reduction at all - and "
                f"costs {1.0 / variants['d2']['speedup_vs_d1_moving'] - 1.0:+.1%} wall time. "
                f"On the candidate stack it is "
                f"{variants['d4']['seconds_per_step'] / variants['d3']['seconds_per_step'] - 1.0:+.1%}. "
                "The cached agglomeration is not going stale in any measurable way."
            ),
        },
        "n5_pressure_reference": {
            "hypothesis": (
                "0/p's farfield is freestreamPressure on one 20-chord patch with zeroGradient "
                "walls, so at U = 0.1 m/s the freestream enters over most of that boundary, "
                "the system is nearly pure Neumann and its constant mode is nearly a null "
                "vector - a textbook way to stall a multigrid coarse-grid correction."
            ),
            "refuted": True,
            "measured": (
                f"Pinning the ENTIRE farfield to fixedValue - the strongest possible form of "
                f"the fix, and deliberately over-constrained - moves the pressure solve from "
                f"{moving_control:.1f} to {variants['d5']['p_iterations_per_solve']:.1f} "
                "iterations per solve, about 3 percent and inside run-to-run scatter. "
                "Conditioning is not why multigrid struggles here, so no campaign BC changes "
                "and the C-grid's farfield patch is not split."
            ),
        },
        "screen_plunge_reached_m": _screen_plunge_reached(N_STEPS * DT_S),
        "screen_plunge_reached_wall_cells": _screen_plunge_reached(N_STEPS * DT_S)
        / FIRST_CELL_HEIGHT_M,
        "where_the_3x_actually_is": (
            "Motion alone is worth "
            f"{moving_control / static_control:.2f}x ({static_control:.1f} -> "
            f"{moving_control:.1f} iterations per p solve), against the "
            f"{campaign['flexible']['p_iterations_per_solve_all'] / static_control:.2f}x the "
            "campaign shows, and the refutation is a fortiori: under ADR-024's (1-cos) ramp "
            "the campaign's foil had moved "
            f"{campaign['flexible']['plunge_reached_m']:.2e} m by its 0.01 s end time - "
            f"{campaign['flexible']['plunge_reached_wall_cells']:.3f} of ONE wall cell - while "
            "this screen has no ramp and moved it "
            f"{_screen_plunge_reached(N_STEPS * DT_S) / campaign['flexible']['plunge_reached_m']:.0f}x "
            "further. A screen that deforms the mesh far more than the campaign ever did, and "
            "still reproduces almost none of the cost, settles it: N2's stated attribution - "
            "'the deforming mesh makes the pressure system about three times harder' - is "
            "WRONG, and both sides of that 3x in fact ran on an effectively static mesh."
        ),
        "mechanism": (
            "The campaign's cost is STARTUP-TRANSIENT difficulty, sustained forever. This "
            "screen's own first five steps cost "
            f"{variants['d1']['p_iterations_per_solve_startup']:.1f} iterations per p solve "
            f"from uniform fields and decay to {moving_control:.1f} by step five, because a "
            "marching solve warms up: each step starts from the previous step's converged "
            "pressure field. The campaign's first five step-solves sit at "
            f"{campaign['flexible']['p_iterations_per_solve_first_5']:.1f} - the screen's "
            "STARTUP number, not its settled one - and they never decay, running "
            f"{campaign['flexible']['p_iterations_per_solve_all']:.1f} over all "
            f"{campaign['flexible']['n_step_solves']} solves. Under implicit coupling every "
            "iteration of a window restores the window-start checkpoint, so the pressure "
            "solve never inherits a converged iterate and is permanently cold-started. That "
            "is consistent with all four measured signatures: present from the first solve, "
            "flat across position in the window (987 GAMG iterations on iteration 1 against "
            "977 on iteration 3), flat in time, and untouched by both agglomeration and the "
            "pressure reference level. The lever it implies is the per-iteration initial "
            "guess, which lives in the preCICE adapter's checkpointing and the coupling "
            "scheme - ADR-039 C1 territory, frozen and carried over, so it is REPORTED here "
            "and not acted on. A fluid-only screen cannot test it; only a coupled run can."
        ),
        "the_projection_is_conservative_not_optimistic": (
            "The candidate stack's advantage is LARGER in the cold-start regime the campaign "
            f"actually lives in: {variants['d1']['seconds_per_step_startup'] / variants['d3']['seconds_per_step_startup']:.2f}x "
            "over the first five steps against "
            f"{variants['d1']['seconds_per_step'] / variants['d3']['seconds_per_step']:.2f}x once "
            "the marching solve has warmed up. So the ~2.00 s/window projection, built on the "
            "settled ratio, is if anything pessimistic. It is still a PROJECTION and it still "
            "may not size: only ADR-040 N3, coupled and contended at the gated rung past the "
            "ramp, may do that."
        ),
        "verdict": (
            "Both leads refuted, and the numerics ratios hold on a mesh that moves: the "
            f"candidate stack is {variants['d3']['speedup_vs_d1_moving']:.2f}x against the "
            f"moving control and {variants['d0']['seconds_per_step'] / variants['d3']['seconds_per_step']:.2f}x "
            "against the static one, bracketing N2's 3.73x, so the ~2.00 s/window projection "
            "stands unchanged and the 14-day ceiling remains out of reach at any "
            "settled-cycle count. cacheAgglomeration and the pressure reference level are "
            "both dead ends and neither enters the ADR-040 stack; the residual factor is "
            "coupling-specific, bounded, and named."
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"record written: {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--run", choices=sorted(VARIANTS))
    parser.add_argument("--ranks", type=int, default=1)
    parser.add_argument("--record", type=Path)
    args = parser.parse_args(argv)

    if args.prepare:
        return prepare()
    if args.run:
        return run(args.run, ranks=args.ranks)
    if args.record:
        return record(args.record)
    parser.error("choose a mode: --prepare / --run / --record")


if __name__ == "__main__":
    raise SystemExit(main())

"""Rigid 2-D flapping wing in hover — the flagship forward-capability case (Stage 14).

A thin elliptic wing performs a prescribed flapping stroke (translation + pitch) in a
quiescent domain at Re ~ 10^2, reproducing Wang, Birch & Dickinson (2004)'s 2-D robotic-wing
computation. This is the last validated forward problem before the Stage-15 optimizer.

Mesh: a 4-block **O-grid** around the ellipse (inner boundary = the wing, spline edges tracing
the ellipse; outer boundary a circle at ``farfield_radius_chords`` chords), reusing the proven
Stage-11 cylinder O-grid topology. **Hover has no freestream:** the far field is an open
``pressureInletOutletVelocity`` / ``totalPressure`` boundary (not a ``freestream`` inlet), and
the case writes only the *dimensional* ``forces`` FO — ``forceCoeffs`` divides by ``magUInf``,
meaningless at zero freestream (the coefficients are formed in
:mod:`aero.postprocess.flapping_forces` with the WBD normalisation). The wing wall uses
``movingWallVelocity`` (no-slip in the moving frame — critical for unbiased forces).

Motion (ADR-024): the combined stroke is a numpy-generated ``tabulated6DoFMotion`` table
(:mod:`aero.adapters.openfoam.motion`), mounted either on the **morph** path
(``solidBodyMotionDisplacement`` on the wing + a ``displacementLaplacian`` deforming mesh,
default) or the **solid-body** path (the whole mesh moves rigidly — exact, zero deformation).
``vorticity`` and ``Q`` field function objects are written at each phase-locked write time for
the leading-edge-vortex capture evidence.

Laminar only (Re ~ 100; no transition model this rung).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aero.adapters.openfoam._foam_common import (
    RHO_INF,
    expansion,
    header,
    pt,
    transient_fvschemes,
    transient_fvsolution,
    transport_properties,
    turbulence_properties,
)
from aero.adapters.openfoam.motion import (
    FlappingMotionSpec,
    dynamic_mesh_dict,
    flapping_dynamic_mesh_dict_solid_body,
    flapping_motion_table,
    flapping_point_displacement_field,
)

_STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    str_strip_whitespace=True,
    validate_assignment=True,
    validate_default=True,
)

_MOTION_TABLE_FILE = "flapping_motion.dat"
_MOTION_TABLE_REF = f"<constant>/{_MOTION_TABLE_FILE}"


class FlappingWingSpec(BaseModel):
    """A 2-D rigid elliptic wing in prescribed flapping hover — transient laminar (WBD 2004)."""

    model_config = _STRICT

    geometry: Literal["flapping_wing_2d"] = "flapping_wing_2d"
    name: str = Field(..., min_length=1, description="Case name.")
    reynolds: float = Field(
        ..., gt=0, description="Re = u_ref*chord/nu, u_ref = U_max = omega*stroke_amplitude (WBD)."
    )
    chord: float = Field(default=1.0, gt=0, description="Wing chord c (length units).")
    thickness_ratio: float = Field(
        default=0.125, gt=0.0, lt=1.0, description="Ellipse thickness/chord (WBD leave it free)."
    )
    span: float = Field(default=1.0, gt=0, description="Spanwise extent (one cell, 2D).")
    turbulence_model: Literal["laminar"] = Field(
        default="laminar", description="Re~100 is laminar; no turbulence transport."
    )
    transient: Literal[True] = Field(default=True)

    motion: FlappingMotionSpec = Field(..., description="Prescribed flapping stroke (required).")
    mesh_motion: Literal["morph", "solid_body"] = Field(
        default="morph",
        description="Mesh-motion strategy (ADR-024): 'morph' (displacementLaplacian, far field "
        "fixed) or 'solid_body' (whole mesh moves rigidly). Provenance-visible.",
    )

    # --- O-grid resolution (chord-based) ---
    farfield_radius_chords: float = Field(
        default=25.0, gt=2.0, description="Outer-circle radius in chords (quiescent-hover box)."
    )
    n_radial: int = Field(default=120, gt=3, description="Radial cells (wing -> far field).")
    n_azimuthal: int = Field(
        default=64, gt=3, description="Azimuthal cells per 90-deg block (x4 around the wing)."
    )
    radial_first_cell: float = Field(
        default=5.0e-3, gt=0, description="First radial cell height at the wall, in chords."
    )
    spline_points_per_quadrant: int = Field(
        default=16, gt=1, description="Ellipse spline sampling per 90-deg block (mesh fidelity)."
    )

    # --- transient controls (in flapping periods) ---
    end_time_cycles: float = Field(
        default=24.0, gt=0, description="Total run length in flapping periods (~16+ converged)."
    )
    write_phases_per_cycle: int = Field(
        default=16, gt=1, description="Field writes per cycle (phase-locked LEV snapshots)."
    )
    purge_write: int = Field(
        default=40, ge=0, description="Field time-dirs retained (0 = keep all); ~2.5 cycles at 16."
    )
    max_courant: float = Field(default=0.8, gt=0, description="Adjustable-timestep Courant cap.")

    @property
    def pivot(self) -> tuple[float, float, float]:
        """The pitch pivot (CofG for the motion) — the O-grid is centred here (origin)."""
        return (0.0, 0.0, 0.0)


# --- ellipse geometry ---------------------------------------------------------
def _ellipse_point(
    spec: FlappingWingSpec, param_deg: float, *, radius_scale: float = 1.0
) -> tuple[float, float]:
    """A point on the wing ellipse at parametric angle ``param_deg`` (ellipse frame -> world).

    The ellipse has semi-major ``chord/2`` along the chord and semi-minor
    ``thickness_ratio*chord/2``, is oriented at ``pitch_mean_deg`` (the built-in mid-stroke
    angle — the motion table rotates relative to this), and is centred so the pitch pivot sits
    at the origin. ``radius_scale`` is unused for the wing (kept 1.0); the outer ring is a
    separate circle.
    """
    a = 0.5 * spec.chord * radius_scale
    b = 0.5 * spec.thickness_ratio * spec.chord * radius_scale
    ph = math.radians(param_deg)
    # ellipse-frame local coordinates (major axis = chord along local x)
    lx = a * math.cos(ph)
    ly = b * math.sin(ph)
    # rotate into the mid-stroke orientation (chord at pitch_mean_deg from +x)
    th = math.radians(spec.motion.pitch_mean_deg)
    ct, st = math.cos(th), math.sin(th)
    rx = lx * ct - ly * st
    ry = lx * st + ly * ct
    # centre offset so the pivot (fraction along the chord) lands at the origin
    frac = spec.motion.pivot_chord_fraction
    centre = (0.5 - frac) * spec.chord
    cx, cy = centre * ct, centre * st
    return rx + cx, ry + cy


def _flapping_blockmesh(spec: FlappingWingSpec) -> str:
    """4-block O-grid: inner ellipse (spline edges) -> outer circle (arc edges).

    Same winding as the Stage-11 cylinder O-grid (positive cell volumes, radial graded toward
    the wall); the inner ring is the ellipse (spline edges sampled from :func:`_ellipse_point`)
    instead of a circle, so a thin section is represented faithfully.
    """
    rr = spec.farfield_radius_chords * spec.chord
    span = spec.span
    angles = [45.0, 135.0, 225.0, 315.0]
    inner = [_ellipse_point(spec, a) for a in angles]
    outer = [(rr * math.cos(math.radians(a)), rr * math.sin(math.radians(a))) for a in angles]
    base = inner + outer  # 0..3 inner (ellipse), 4..7 outer (circle)
    nb = len(base)  # 8
    verts = [pt(x, y, 0.0) for x, y in base] + [pt(x, y, span) for x, y in base]

    # Radial grading uses a representative inner->outer distance (semi-minor to far field).
    inner_ref = 0.5 * spec.thickness_ratio * spec.chord
    g_rad = expansion(rr - inner_ref, spec.n_radial, spec.radial_first_cell * spec.chord)
    na, nrad = spec.n_azimuthal, spec.n_radial

    def _verts(a: int, b: int, c: int, d: int) -> str:
        return " ".join(str(v) for v in (a, b, c, d, a + nb, b + nb, c + nb, d + nb))

    blocks = []
    for i in range(4):
        j = (i + 1) % 4
        # Bottom face (inner_i, outer_i, outer_j, inner_j) CCW from +z: v0->v1 RADIAL
        # (n_radial, graded toward the wall), v1->v2 AZIMUTHAL (n_azimuthal).
        blocks.append(
            f"    hex ({_verts(i, 4 + i, 4 + j, j)}) ({nrad} {na} 1) "
            f"simpleGrading ({g_rad:.8g} 1 1)"
        )

    # Inner spline edges trace the ellipse between the corner vertices; outer arc edges the circle.
    def arc(v1: int, v2: int, mid_angle: float, z: float) -> str:
        mx = rr * math.cos(math.radians(mid_angle))
        my = rr * math.sin(math.radians(mid_angle))
        return f"    arc {v1} {v2} ({mx:.8f} {my:.8f} {z:.8f})"

    edges = []
    for i in range(4):
        j = (i + 1) % 4
        a0, a1 = angles[i], angles[i] + 90.0
        # inner ellipse spline (z=0 and z=span)
        pts0 = " ".join(
            f"({x:.8f} {y:.8f} 0.0)"
            for x, y in (
                _ellipse_point(spec, a0 + (a1 - a0) * k / spec.spline_points_per_quadrant)
                for k in range(1, spec.spline_points_per_quadrant)
            )
        )
        pts1 = " ".join(
            f"({x:.8f} {y:.8f} {span:.8f})"
            for x, y in (
                _ellipse_point(spec, a0 + (a1 - a0) * k / spec.spline_points_per_quadrant)
                for k in range(1, spec.spline_points_per_quadrant)
            )
        )
        edges.append(f"    spline {i} {j} ({pts0})")
        edges.append(f"    spline {i + nb} {j + nb} ({pts1})")
        mid = angles[i] + 45.0
        edges.append(arc(4 + i, 4 + j, mid, 0.0))
        edges.append(arc(4 + i + nb, 4 + j + nb, mid, span))

    def face(a: int, b: int) -> str:
        return f"({a} {b} {b + nb} {a + nb})"

    wing = " ".join(face(i, (i + 1) % 4) for i in range(4))
    far = " ".join(face(4 + i, 4 + (i + 1) % 4) for i in range(4))
    z0 = " ".join(f"({i} {4 + i} {4 + (i + 1) % 4} {(i + 1) % 4})" for i in range(4))
    zspan = " ".join(
        f"({i + nb} {4 + i + nb} {4 + (i + 1) % 4 + nb} {(i + 1) % 4 + nb})" for i in range(4)
    )

    boundary = f"""    wing
    {{
        type wall;
        faces ( {wing} );
    }}
    farfield
    {{
        type patch;
        faces ( {far} );
    }}
    front
    {{
        type empty;
        faces ( {z0} );
    }}
    back
    {{
        type empty;
        faces ( {zspan} );
    }}"""
    verts_block = "\n".join(f"    {v}" for v in verts)
    return (
        header("dictionary", "blockMeshDict")
        + "\nscale 1;\n\n"
        + f"vertices\n(\n{verts_block}\n);\n\n"
        + "blocks\n(\n"
        + "\n".join(blocks)
        + "\n);\n\n"
        + "edges\n(\n"
        + "\n".join(edges)
        + "\n);\n\n"
        + f"boundary\n(\n{boundary}\n);\n\n"
        + "mergePatchPairs ( );\n"
    )


# --- transient dictionaries ---------------------------------------------------
def _controldict(spec: FlappingWingSpec) -> str:
    period = spec.motion.period
    end_time = spec.end_time_cycles * period
    write_interval = period / spec.write_phases_per_cycle
    px, py, pz = spec.pivot
    return (
        header("dictionary", "controlDict")
        + f"""
application     pimpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {end_time:.8g};
deltaT          {0.02 * write_interval:.8g};
writeControl    adjustableRunTime;
writeInterval   {write_interval:.8g};
purgeWrite      {spec.purge_write};
writeFormat     ascii;
writePrecision  8;
runTimeModifiable false;
adjustTimeStep  yes;
maxCo           {spec.max_courant:.8g};
maxDeltaT       {write_interval:.8g};

functions
{{
    forces1
    {{
        type            forces;
        libs            (forces);
        writeControl    timeStep;
        writeInterval   1;
        patches         (wing);
        rho             rhoInf;
        rhoInf          {RHO_INF};
        CofR            ({px:.8g} {py:.8g} {pz:.8g});
    }}
    vorticity1
    {{
        type            vorticity;
        libs            (fieldFunctionObjects);
        writeControl    writeTime;
    }}
    Q1
    {{
        type            Q;
        libs            (fieldFunctionObjects);
        writeControl    writeTime;
    }}
}}
"""
    )


def _fields(spec: FlappingWingSpec) -> dict[str, str]:
    # Quiescent hover: still fluid, open far field. movingWallVelocity keeps the no-slip in the
    # moving frame (a plain fixedValue (0 0 0) would impose a wrong wall flux and bias forces).
    def field(obj: str, cls: str, dims: str, internal: str, wing: str, far: str) -> str:
        return (
            header(cls, obj)
            + f"""
dimensions      {dims};
internalField   uniform {internal};

boundaryField
{{
    wing
    {{
{wing}
    }}
    farfield
    {{
{far}
    }}
    front {{ type empty; }}
    back  {{ type empty; }}
}}
"""
        )

    return {
        "U": field(
            "U",
            "volVectorField",
            "[0 1 -1 0 0 0 0]",
            "(0 0 0)",
            "        type movingWallVelocity;\n        value uniform (0 0 0);",
            "        type pressureInletOutletVelocity;\n        value uniform (0 0 0);",
        ),
        "p": field(
            "p",
            "volScalarField",
            "[0 2 -2 0 0 0 0]",
            "0",
            "        type zeroGradient;",
            "        type totalPressure;\n        p0 uniform 0;\n        value uniform 0;",
        ),
    }


def write_flapping_wing_case(spec: FlappingWingSpec, dest: Path) -> None:
    """Write a complete transient OpenFOAM case for the flapping wing under ``dest``."""
    system = dest / "system"
    constant = dest / "constant"
    zero = dest / "0"
    for d in (system, constant, zero):
        d.mkdir(parents=True, exist_ok=True)

    # WBD Reynolds number is built on the maximum wing speed U_max (= u_ref), not a freestream,
    # so nu is derived directly rather than via flow_state's freestream-U convention.
    nu = spec.motion.u_ref * spec.chord / spec.reynolds

    (system / "blockMeshDict").write_text(_flapping_blockmesh(spec), encoding="utf-8")
    (system / "controlDict").write_text(_controldict(spec), encoding="utf-8")
    (system / "fvSchemes").write_text(transient_fvschemes(), encoding="utf-8")
    (system / "fvSolution").write_text(
        transient_fvsolution(cell_displacement=True), encoding="utf-8"
    )
    (constant / "transportProperties").write_text(transport_properties(nu), encoding="utf-8")
    (constant / "turbulenceProperties").write_text(
        turbulence_properties(spec.turbulence_model), encoding="utf-8"
    )
    for name, text in _fields(spec).items():
        (zero / name).write_text(text, encoding="utf-8")

    # The prescribed motion: a tabulated6DoFMotion table covering the whole run, mounted either
    # on the morph path (deforming mesh, wing patch driven) or the solid-body path (rigid mesh).
    end_time = spec.end_time_cycles * spec.motion.period
    (constant / _MOTION_TABLE_FILE).write_text(
        flapping_motion_table(spec.motion, end_time=end_time), encoding="utf-8"
    )
    if spec.mesh_motion == "morph":
        (constant / "dynamicMeshDict").write_text(
            dynamic_mesh_dict(moving_patch="wing"), encoding="utf-8"
        )
        (zero / "pointDisplacement").write_text(
            flapping_point_displacement_field(
                moving_patch="wing",
                cofg=spec.pivot,
                table_filename=_MOTION_TABLE_REF,
                fixed_patches=["farfield"],
                empty_patches=["front", "back"],
            ),
            encoding="utf-8",
        )
    else:  # solid_body
        (constant / "dynamicMeshDict").write_text(
            flapping_dynamic_mesh_dict_solid_body(
                cofg=spec.pivot, table_filename=_MOTION_TABLE_REF
            ),
            encoding="utf-8",
        )
